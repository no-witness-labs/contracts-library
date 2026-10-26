#!/usr/bin/env python3
"""Universal checks (prototype): generate Blaster obligations from a blueprint, run them, report.

The developer supplies only the compiled validator (plutus.json). This script
reads the blueprint, writes a Base module per validator (the script, the datum
and redeemer shapes, the generic transaction) and one module per check, builds
the check modules in parallel, each with a time limit, and prints a report with
the waivers from universal.json applied.

The transaction is generic: every list in the script context that the shape
covers holds up to two items and Blaster decides which are present (the Bool
"shape" flags); every value is open; every sum type in the datum or redeemer
is a Bool-selected choice between its constructors, and full mode writes one
module per combination of constructors, up to `--max-cases` per check
(`--quick` pins each sum to its first constructor, which is faster and weaker). The ledger rules
(validScriptContext) are a hypothesis on the spend checks. What the shape does
not cover is in Universal/Notes.lean; a PASS holds within the shape.

Usage, from formal/:
  scripts/universal.py --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
  scripts/universal.py --blueprint ../onchain/plutus.json linear_vesting
  scripts/universal.py --blueprint ../onchain/plutus.json --quick linear_vesting
  scripts/universal.py --blueprint ../onchain/plutus.json --no-run linear_vesting   # generate only
Exit code: 1 when any HOLE remains; 2 when any check has no verdict (UNDETERMINED, UNREACHED or
UNKNOWN), which wins over 1; 0 otherwise.
"""
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# Each undeclared purpose is tested on a context that carries that purpose's witness
# (the redeemer entry, the withdrawal, the certificate, the vote or the proposal), so a
# fallback keyed on the witness is exercised. The checks are unconditional.
PURPOSES = {
    "mint": {
        "info": "(.MintingScript cs)", "key": "(.Minting cs)", "binders": "(cs : ByteString)",
        "overrides": "txInfoMint := [(Data.B cs, Data.Map [(Data.B h.name, Data.I h.qty)])]",
        "consequence": "accepted a mint or burn under this script's hash; if the fallback is meant to handle "
                       "minting, declare the handler, otherwise anyone can mint"},
    "withdraw": {
        "info": "(.RewardingScript (.ScriptCredential cred))", "key": "(.Rewarding (.ScriptCredential cred))",
        "binders": "(cred : ByteString)", "overrides": "txInfoWdrl := [(.ScriptCredential cred, 0)]",
        "consequence": "accepted a reward withdrawal for this script's credential; if the fallback is meant to "
                       "handle it, declare the handler, otherwise anyone can take the rewards"},
    "publish": {
        "info": "(.CertifyingScript 0 (.TxCertRegStaking (.ScriptCredential cred) none))",
        "key": "(.Certifying 0 (.TxCertRegStaking (.ScriptCredential cred) none))", "binders": "(cred : ByteString)",
        "overrides": "txInfoTxCerts := [.TxCertRegStaking (.ScriptCredential cred) none]",
        "consequence": "accepted a certificate for this script's credential (register, delegate, retire); "
                       "declare the handler or anyone can publish them"},
    "vote": {
        "info": "(.VotingScript (.DRepVoter (.ScriptCredential cred)))", "key": "(.Voting (.DRepVoter (.ScriptCredential cred)))",
        "binders": "(cred : ByteString)", "overrides": "txInfoVotes := [(.DRepVoter (.ScriptCredential cred), [])]",
        "consequence": "accepted a vote with this script as a DRep; declare the handler or anyone can vote with it"},
    "propose": {
        "info": "(.ProposingScript 0 ⟨0, .ScriptCredential cred, Data.I 0⟩)", "key": "(.Proposing 0 ⟨0, .ScriptCredential cred, Data.I 0⟩)",
        "binders": "(cred : ByteString)", "overrides": "txInfoProposalProcedures := [⟨0, .ScriptCredential cred, Data.I 0⟩]",
        "consequence": "accepted a governance proposal guarded by this script; declare the handler or anyone can propose"},
}

# The shape flags (Bool) and open values of the generic transaction.
FLAGS = ["in2", "out2", "out1Script", "out1Foreign", "sig1", "sig2", "mint1", "lowFin"]
BYTES = ["s1", "s2", "payee", "payee2", "policy", "name"]
INTS = ["inLov", "inLov2", "outLov", "outLov2", "qty", "lo", "fee"]
# No output on chain holds less: 4,310 lovelace per byte times the 160-byte overhead (CIP-55).
# Universal claims assume only this, so a PASS covers every amount the ledger allows.
LEDGER_FLOOR = 689_600
# Witnesses of existence claims hold at least 1 ada everywhere, so they are not dust. Stricter than
# the ledger, and still not exact: an output with a datum and tokens can need more.
WITNESS_MIN = 1_000_000

NO_VALIDITY = False
NO_PREP = True
PREP_STEPS = 60000
QUICK = False
TIMEOUT = 600  # seconds per module, wall clock; a slower module is stopped and reports UNDETERMINED
MAX_CASES = 16  # modules per check in full mode; sums that do not fit stay open inside each module


def resolve(ref, defs):
    key = ref.split("/")[-1].replace("~1", "/")
    return defs[key]


@dataclass
class Choice:
    """One sum type: n constructors chosen by n - 1 nested Bool flags. The first flag picks the
    first constructor, the next the second, and all false the last. `nested` holds, per
    constructor, the sums inside its fields, which matter only when that constructor is chosen."""
    title: str
    ctors: list
    flags: list
    nested: list

    def select(self, k):
        """The hypotheses that pick constructor k."""
        return [f"h.{f} = false" for f in self.flags[:k]] + ([f"h.{self.flags[k]} = true"] if k < len(self.flags) else [])


class DataGen:
    """Build a Data term with the blueprint's shape: symbolic leaves, a Bool choice per sum type."""

    def __init__(self, defs, prefix, label="", ref="h."):
        self.defs = defs
        self.prefix = prefix  # every leaf name starts with it; it holds "_", so no fixed field collides
        self.label = label  # how the report names this term's sums, e.g. "output "
        self.ref = ref  # how a term refers to a leaf: a field of the `h : Holes` argument
        self.binders = []  # (field name, lean type)
        self.choices = []  # the outermost sums of the terms built so far
        self.n = 0

    def fresh(self, ty, hint):
        self.n += 1
        name = f"{self.prefix}{hint}{self.n}"
        self.binders.append((name, ty))
        return f"{self.ref}{name}"

    def gen(self, schema, hint="x", title=None):
        if "$ref" in schema:
            key = schema["$ref"].split("/")[-1]
            if key == "Data":
                return f"Data.I {self.fresh('Int', 'any')}"  # any Data: an open integer stands in
            return self.gen(resolve(schema["$ref"], self.defs), hint, title)
        if "anyOf" in schema:
            if QUICK or len(schema["anyOf"]) == 1:
                return self.gen(schema["anyOf"][0], hint, title)  # quick mode, or nothing to choose
            outer, branches, nested = self.choices, [], []
            for c in schema["anyOf"]:
                self.choices = []
                branches.append(self.gen(c, hint, title))
                nested.append(self.choices)
            self.choices = outer
            flags, term = [], branches[-1]
            for k in range(len(branches) - 2, -1, -1):
                flag = self.fresh("Bool", "c")
                flags.insert(0, flag[len(self.ref):])
                term = f"(if {flag} then {branches[k]} else {term})"
            ctors = [c.get("title") or str(c.get("index")) for c in schema["anyOf"]]
            self.choices.append(Choice(self.label + (title or hint), ctors, flags, nested))
            return term
        dt = schema.get("dataType")
        if dt == "constructor":
            # a field's title is its path from the datum, e.g. owner.payment_credential, so the report can name it
            path = lambda f: f"{title}.{f['title']}" if title and f.get("title") else (f.get("title") or title)
            fields = [self.gen(f, (f.get("title") or hint)[:8], path(f)) for f in schema.get("fields", [])]
            return f"Data.Constr {schema['index']} [{', '.join(fields)}]"
        if dt == "bytes":
            return f"Data.B {self.fresh('ByteString', hint)}"
        if dt == "integer":
            return f"Data.I {self.fresh('Int', hint)}"
        if dt == "list":
            if "items" in schema:
                return f"Data.List [{self.gen(schema['items'], hint, title)}]"  # one element (bounded shape)
            return "Data.List []"
        if dt == "map":
            return "Data.Map []"
        return f"Data.I {self.fresh('Int', 'any')}"

    def variants(self, schema, hint):
        """One (name, term, constructor count, sums) per top-level redeemer constructor; else one
        unnamed term. Each action keeps its own sums, so they split only that action's checks."""
        if "$ref" in schema and schema["$ref"].split("/")[-1] != "Data":
            schema = resolve(schema["$ref"], self.defs)
        ctors = schema["anyOf"] if "anyOf" in schema and all(c.get("dataType") == "constructor" for c in schema["anyOf"]) else None
        out = []
        for c in (ctors or [schema]):
            self.choices = []
            term = self.gen(c, hint)
            out.append(((c.get("title") or f"c{c['index']}") if ctors else "", term, len(ctors or []), self.choices))
        self.choices = []
        return out


@dataclass
class Decl:
    """One Lean declaration, kept in parts so a case adds its hypotheses without editing text.
    `falsify` states a universal claim Blaster must falsify: its counterexample is the witness."""
    name: str
    doc: str
    claim: str
    hyps: list = field(default_factory=list)  # lines of hypotheses, each joined with →
    binders: str = ""  # extra binders after `h`, e.g. "∀ m : Int,"
    falsify: bool = False
    part: str = ""  # names the module when a check has more than one declaration


def render(decl, case_hyps, suffix):
    """The declaration for one case: the case's hypotheses first, then the check's own."""
    name = decl.name + suffix
    head = "∀ h : Holes," + (f" {decl.binders}" if decl.binders else "")
    lines = [f"    {line} →" for line in ([" → ".join(case_hyps)] if case_hyps else []) + decl.hyps]
    if decl.falsify:
        return ([f"/-- {decl.doc} -/", f"def {name} : Prop := {head}"] + lines + [f"    {decl.claim}",
                 "-- A solver timeout is a warning on this command; as an error it fails the build.",
                 "set_option warningAsError true in",
                 f"#blaster (timeout: {TIMEOUT}) (solve-result: 1) [{name}]"])
    return ([f"/-- {decl.doc} -/", f"theorem {name} : {head}"] + lines + [f"    {decl.claim} := by",
             f"  blaster (timeout: {TIMEOUT})"])


OPENS = [
    "open PlutusCore.UPLC.Term (Program)",
    "open PlutusCore.ByteString (ByteString)",
    "open PlutusCore.Data (Data)",
    "open CardanoLedgerApi.IsData.Class (IsData)",
    "open CardanoLedgerApi.V3 (Address ScriptContext ScriptInfo ScriptPurpose TxInfo TxInInfo TxOut Value)",
    "open CardanoLedgerApi.V1.Time (POSIXTimeRange after everything)",
    "open PlutusCore.UPLC.Utils (isSuccessful isUnsuccessful)",
]


def header_notes(name):
    return f"""/-!
# Universal checks for `{name}`

Security checks that apply to any compiled validator, instantiated on this one from its
blueprint. Nothing here was written by the validator's author. Design notes, limits and the
review history are in `Universal/Notes.lean`; this header is the short form.

## What is open

Every open value is a field of the `Holes` structure below; each check quantifies over one
`h : Holes` and pins the fields it needs with hypotheses. The transaction is composed from the
builders in `Universal.Harness`.

- Shape flags: a second script input, a second output, where the first output goes (own script,
  a key, another script), two signers, one minted asset, a finite or absent lower validity bound.
- Every value: lovelace amounts, fee, signers, policy, asset name, quantity, times.
- The datum of the own input and the datum of the continuing output, each with the blueprint's
  shape, independent leaves and a Bool choice per sum type{' (pinned to the first constructor: quick mode)' if QUICK else ''}.
- One redeemer per declared action, same treatment; any `Data` leaf is an open integer.

## What is not in the shape

No reference inputs, no withdrawals on spends, no certificates, no datum hashes, no tokens on
inputs, at most two of each list, one item in each list inside a datum, no finite upper validity
bound. A PASS holds within the shape; a contract whose accept path needs one of these shows UP-000
as REVIEW and its other checks as UNREACHED. The script hash is a placeholder, used consistently.

## Reading the verdicts

`#blaster (solve-result: 1)` means the stated universal claim must be falsified: the counterexample
is a working transaction Blaster found. A `theorem ... := by blaster` must hold. `valid` is the
ledger rule set from CardanoLedgerApi. `ledgerFloor` is the minimum the ledger puts on every output,
so a theorem that assumes only that covers every amount the chain allows; `realistic` asks 1 ada of
every amount, so a witness is not dust. A Blaster `Valid` is an SMT verdict with no proof term, as
everywhere in this repository. One module per check and case, so lake builds them in parallel.
-/"""


def generate(name, hex_code, declared, datum_term, out_datum_term, redeemer_variants, leaves, choices=(), out_choices=()):
    # choices, out_choices: the outermost sums of the input datum and of the continuing output's datum
    """Return (module name, base source, [(check module name, source)], obligations)."""
    mod = name[0].upper() + name[1:]
    ns = f"Universal.Demo.{mod}"
    # #prep_uplc declares its name outside any namespace, so two contracts must not share it:
    # a file importing both would fail. Name it after the validator.
    camel = "".join(part[:1].upper() + part[1:] for part in name.split("_"))
    prep_id = f"universal{camel}Prepared"
    undeclared = [p for p in PURPOSES if p not in declared]
    fields = [(f, "Bool") for f in FLAGS] + list(leaves) + [(x, "ByteString") for x in BYTES] + [(x, "Int") for x in INTS]

    # ---- Base module: the script, the holes, the transaction composed from the harness ----
    b = [f"-- Generated by scripts/universal.py from the blueprint entry `{name}`. Do not edit; regenerate.",
         "import Blaster", "import PlutusCore.UPLC", "import CardanoLedgerApi.V3", "import CardanoLedgerApi.V1.Time",
         "import PlutusCore.UPLC.PreProcess", "import Formal.Common", "import Universal.Harness", "",
         header_notes(name), "", f"namespace {ns}", ""] + OPENS + ["open Universal.Harness", ""]
    # The compiled code sits in this file, so a new build of the contract changes the file and
    # lake rebuilds every check; a separate script file would leave the old build in the cache.
    b += ["/-- The compiled validator, as the blueprint holds it. -/",
          "abbrev script : PlutusCore.UPLC.PlutusScript.PlutusScript :=",
          f'  ⟨.PlutusV3, singleCborEncodedScriptFromHexM "{hex_code}"⟩']
    if NO_PREP:
        b.append("def validator : Program := script.script")
        b.append("def accepts (ctx : ScriptContext) : Prop := Formal.Common.validatorAccepts ctx validator")
        b.append("def rejects (ctx : ScriptContext) : Prop := Formal.Common.validatorRejects ctx validator")
    else:
        b.append("def allInputs (ctx : ScriptContext) : List PlutusCore.UPLC.Term.Term := [CardanoLedgerApi.IsData.Class.toTerm ctx]")
        b.append(f"#prep_uplc {prep_id} script allInputs {PREP_STEPS}")
        b.append(f"def accepts (ctx : ScriptContext) : Prop := isSuccessful ({prep_id}.prop ctx)")
        b.append(f"def rejects (ctx : ScriptContext) : Prop := isUnsuccessful ({prep_id}.prop ctx)")
    if NO_VALIDITY:
        b.append("def valid (_ctx : ScriptContext) : Prop := True")
    else:
        b.append("/-- Ledger rules (CardanoLedgerApi): a counterexample must be a transaction the chain would accept. -/")
        b.append("def valid (ctx : ScriptContext) : Prop := CardanoLedgerApi.V3.Contexts.validScriptContext ctx = true")
    b += ["", "/-- Every open value of a spend of this validator, one field each. Blaster fills them. -/",
          "structure Holes where"] + [f"  {n} : {t}" for n, t in fields]
    b += ["", "/-- The ledger's minimum on every output, which the model does not enforce: 4,310 lovelace per byte",
          "    times the 160-byte overhead (CIP-55). Every real transaction meets it. -/",
          "def ledgerFloor (h : Holes) : Prop :=",
          f"  {LEDGER_FLOOR} ≤ h.inLov ∧ {LEDGER_FLOOR} ≤ h.inLov2 ∧ {LEDGER_FLOOR} ≤ h.outLov ∧ {LEDGER_FLOOR} ≤ h.outLov2",
          "/-- At least 1 ada everywhere: what a witness must hold, so it is not dust. -/",
          "def realistic (h : Holes) : Prop :=",
          f"  {WITNESS_MIN} ≤ h.inLov ∧ {WITNESS_MIN} ≤ h.inLov2 ∧ {WITNESS_MIN} ≤ h.outLov ∧ {WITNESS_MIN} ≤ h.outLov2",
          "",
          'def own : ByteString := "fake_script_hash_28bytes!!!!"',
          'def ownRef : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 0⟩',
          'def ref2 : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 1⟩',
          "",
          "/-- Datum of the script's own input, with the blueprint's shape; sums chosen by flags in `h`. -/",
          f"def datum (h : Holes) : Data := {datum_term}",
          "/-- Datum of the continuing output: same shape, its own fields and flags, so it may differ from the input's. -/",
          f"def datumOut (h : Holes) : Data := {out_datum_term}",
          "/-- Redeemers with the blueprint's shape, one per constructor. -/"]
    for rname, rterm, _, _ in redeemer_variants:
        b.append(f"def redeemer{rname} (h : Holes) : Data := {rterm}")
    b += ["",
          "/-- The transaction body, composed from the harness builders. `od` is the continuing output's datum. -/",
          "def txOf (h : Holes) (od r : Data) : TxInfo :=",
          "  let d := datum h",
          "  let minted := token h.mint1 h.policy h.name h.qty",
          "  tx (scriptInput ownRef own (ada h.inLov) d :: optList h.in2 (scriptInput ref2 own (ada h.inLov2) d))",
          "     (outputWithDatum (destination h.out1Script h.out1Foreign own h.payee) (ada h.outLov ++ minted) od",
          "       :: optList h.out2 (payment (keyAddress h.payee2) (ada h.outLov2)))",
          "     h.fee minted (validity h.lowFin h.lo) (upTo2 h.sig1 h.sig2 h.s1 h.s2)",
          "     ((.Spending ownRef, r) :: optList h.in2 (.Spending ref2, r))",
          "",
          "/-- A spend of the own input. The continuing output carries its own datum, so it may differ from the input's. -/",
          "def ctx (h : Holes) (r : Data) : ScriptContext := spending (txOf h (datumOut h) r) ownRef (datum h) r",
          "/-- The script invoked for another purpose: the purpose's witness and redeemer entry are added. -/",
          "def otherCtx (info : ScriptInfo) (key : ScriptPurpose) (rp : Data) (t : TxInfo) : ScriptContext :=",
          "  { scriptContextTxInfo := { t with txInfoRedeemers := (key, rp) :: t.txInfoRedeemers }",
          "    scriptContextRedeemer := rp",
          "    scriptContextScriptInfo := info }",
          "", f"end {ns}"]
    base_src = "\n".join(b) + "\n"

    # ---- One module per check, declaration and case ----
    modules = []
    obligations = []

    # Full mode splits a check into one module per combination of constructors: each choice is a
    # hypothesis, so each module explores one combination. The hypotheses go in as parts of the
    # declaration (`render`), never by editing rendered text.
    def combinations(choice_list, deep):
        """Every combination of constructors, as (hypotheses, labels). `deep` also splits the sums
        nested inside a chosen constructor; otherwise those stay open inside the module."""
        result = [([], [])]
        for ch in choice_list:
            opts = [(ch.select(k) + hs, [f"{ch.title} is {ctor}"] + ls)
                    for k, ctor in enumerate(ch.ctors)
                    for hs, ls in (combinations(ch.nested[k], deep) if deep else [([], [])])]
            result = [(h1 + h2, l1 + l2) for h1, l1 in result for h2, l2 in opts]
        return result

    def split(choice_list):
        """At most MAX_CASES cases: every combination when they fit, else the outermost sums only,
        as many as fit, in order. A sum left out is still an open choice inside each module, so
        every combination stays covered, in fewer and harder modules."""
        cases = combinations(choice_list, True)
        if len(cases) <= MAX_CASES:
            return cases
        kept = []
        for ch in choice_list:
            if len(combinations(kept + [ch], False)) <= MAX_CASES:
                kept.append(ch)
        return combinations(kept, False)

    def check(mod_name, oid, title, expect, consequence, severity, action, decls, sums, default_on=True):
        for hyps, labels in split(sums):
            suffix = "".join(f"_{x.split()[0][2:]}{x.split()[-1][0]}" for x in hyps)  # h.d_c3 = true -> _d_c3t
            label = ", ".join(labels)
            for decl in decls:
                part = f"_{decl.part}" if decl.part else ""
                module = f"{ns}.{mod_name}{part}{suffix}"
                desc = ", ".join(x for x in (decl.part.replace("_", " "), label) if x)
                lines = [f"-- Generated by scripts/universal.py: {oid} for `{name}`{f' ({desc})' if desc else ''}. Do not edit; regenerate.",
                         f"import {ns}.Base", "", f"namespace {ns}", ""] + OPENS + ["open Universal.Harness", ""] + \
                    render(decl, hyps, suffix) + ["", f"end {ns}"]
                modules.append((module, "\n".join(lines) + "\n"))
                obligations.append({"id": f"{oid}{f':{decl.part}' if decl.part else ''}{f'#{suffix}' if suffix else ''}",
                                    "group": oid, "case": desc, "case_key": tuple(hyps),
                                    "module": module, "title": title, "expect": expect,
                                    "severity": severity, "action": action, "default_on": default_on,
                                    "consequence": consequence, "fields": [n for n, _ in fields]})

    typed_redeemer = redeemer_variants[0][0] != ""
    n_ctors = redeemer_variants[0][2]
    pin = "h.out1Foreign = false"  # only UP-011 lets the output go to another script
    datums = list(choices) + list(out_choices)

    for rname, _, _, rsums in redeemer_variants:
        tag = f"/{rname}" if rname else ""
        act = rname or "spend"
        sums = datums + rsums  # every spend check of an action splits on the same sums
        c = f"ctx h (redeemer{rname} h)"
        check(f"UP000_{act}", f"UP-000{tag}", f"sanity: action `{act}` is reachable", "Falsified",
              "no spend of the generated shapes is accepted: funds locked, or the action needs something the "
              "shape lacks (reference inputs, withdrawals, tokens on inputs, a third output)", "review", act, [
                  Decl(f"alwaysRejects{rname}", f"UP-000{tag}: is any realistic valid spend with this action accepted? Blaster must FALSIFY this.",
                       f"rejects ({c})", [pin, f"valid ({c}) → realistic h"], falsify=True)], sums)
        check(f"UP004_{act}", f"UP-004{tag}", f"action `{act}` is not always accepted", "Falsified",
              "this action accepts every realistic valid transaction of the generated shapes: an always-true branch",
              "hole", act, [
                  Decl(f"alwaysAccepts{rname}", f"UP-004{tag}: is any realistic valid spend with this action rejected? Blaster must FALSIFY this.",
                       f"accepts ({c})", [pin, f"valid ({c}) → realistic h"], falsify=True)], sums)
        check(f"UP002_{act}", f"UP-002{tag}", f"action `{act}` rejects a spend with no signatories", "Valid",
              "this action can be spent without any signature; by design only for scripts authenticated another way",
              "review", act, [
                  Decl(f"up002_{act}", f"UP-002{tag}: a valid spend with no signatories is rejected (waive it for permissionless scripts).",
                       f"rejects ({c})", [f"h.sig1 = false → h.sig2 = false → {pin}", f"valid ({c}) → ledgerFloor h"])], sums)
        at = f"ctx {{ h with out1Script := true }} (redeemer{rname} h)"
        moved = f"ctx {{ h with out1Script := false }} (redeemer{rname} h)"
        # `payee` names the other script when the output moves to one; without `≠ own` the solver
        # could name the own script, and the moved output would equal the original.
        check(f"UP011_{act}", f"UP-011{tag}", f"action `{act}`: moving the continuing output is rejected", "Valid",
              "the same spend was accepted with the output moved elsewhere; confirm that paying out is intended "
              "for this action and this case, otherwise the datum can be hijacked", "review", act, [
                  Decl(f"up011_{act}", f"UP-011{tag}: a spend accepted with its output back at the script, whatever datum that output carries within the shape, is rejected once that output moves to a key or another script.",
                       f"accepts ({at}) → rejects ({moved})",
                       ["h.payee ≠ own", f"valid ({at}) → valid ({moved}) → ledgerFloor h"])], sums)

    if typed_redeemer:
        check("UP005", "UP-005", "rejects a malformed redeemer", "Valid",
              "a redeemer that matches no declared action is accepted", "hole", "", [
                  Decl("up005_integer_redeemer", "UP-005: a valid spend whose redeemer is an integer is rejected.",
                       "rejects (ctx h (Data.I m))", [pin, "valid (ctx h (Data.I m)) → ledgerFloor h"],
                       binders="∀ m : Int,", part="integer_redeemer"),
                  Decl("up005_unknown_constructor", "UP-005: a valid spend whose redeemer is a constructor the type lacks is rejected.",
                       "rejects (ctx h (Data.Constr k []))", [f"{n_ctors} ≤ k → {pin}", "valid (ctx h (Data.Constr k [])) → ledgerFloor h"],
                       binders="∀ k : Nat,", part="unknown_constructor")], datums)

    for p in undeclared:
        spec = PURPOSES[p]
        check(f"UP001_{p}", f"UP-001/{p}", f"rejects undeclared purpose `{p}`", "Valid", spec["consequence"], "hole", "", [
            Decl(f"up001_{p}", f"UP-001/{p}: the script declares no `{p}` handler, so it must reject that purpose, even with the purpose's witness present.",
                 f"rejects (otherCtx {spec['info']} {spec['key']} (Data.I rp)\n      {{ txOf h (datum h) (Data.I rp) with {spec['overrides']} }})",
                 [pin], binders=f"∀ (rp : Int) {spec['binders']},")], list(choices))
    return mod, base_src, modules, obligations


LOC = re.compile(r"([A-Za-z0-9_./-]+\.lean):(\d+):(\d+):")
# Blaster's messages (Blaster/Smt/Env.lean), and what each says about the claim as stated. A theorem
# that comes back undetermined is left with an unsolved goal and no Blaster message of its own.
VERDICTS = [("❌ Unexpected Valid", "Valid"), ("✅ Valid", "Valid"),
            ("✅ Expected Falsified", "Falsified"), ("❌ Falsified", "Falsified"),
            ("✅ Expected Undetermined", "Undetermined"), ("⚠️ Undetermined", "Undetermined"),
            ("unsolved goals", "Undetermined")]


def terms(text):
    """Split a printed Lean application into its top-level arguments: an atom, a string literal,
    or a parenthesised term, whatever line breaks Lean put inside them."""
    out, i, n = [], 0, len(text)

    def skip_string(i):
        i += 1
        while i < n and text[i] != '"':
            i += 2 if text[i] == "\\" else 1
        return i + 1

    while i < n:
        if text[i].isspace():
            i += 1
            continue
        start = i
        if text[i] == "(":
            depth = 0
            while i < n:
                if text[i] == '"':
                    i = skip_string(i)
                    continue
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                i += 1
                if depth == 0:
                    break
        elif text[i] == '"':
            i = skip_string(i)
        else:
            while i < n and not text[i].isspace() and text[i] not in "()":
                i += 1
        out.append(text[start:i])
    return out


def parse_witness(msgs, fields):
    """Blaster prints one `- name: value` line per open variable; a value Lean wraps continues on
    the following unlocated lines. A `Holes` value is split into its fields, in declaration order."""
    entries = []
    for line in msgs:
        if LOC.search(line):
            m = re.search(r":\s*- (\w+): (.*)$", line)
            entries.append([m.group(1), m.group(2)] if m else None)
        elif entries and entries[-1] is not None:
            entries[-1][1] += " " + line.strip()
    clean = lambda v: v.replace("PlutusCore.ByteString.PlutusCore.ByteStringInternal.ByteString.mk ", "")
    witness = []
    for name, value in filter(None, entries):
        value = value.strip()
        args = terms(value[1:-1]) if value.startswith("(") and value.endswith(")") else []
        if args and args[0].endswith(".Holes.mk"):
            witness += [f"{f} = {clean(v)}" for f, v in zip(fields, args[1:])]
        else:
            witness.append(f"{name} = {'any value' if value.startswith('$') else clean(value)}")
    return witness


def lake(nix_shell, modules):
    cmd = ["lake", "build"] + modules
    return ["nix", "develop", nix_shell, "-c"] + cmd if nix_shell else cmd


def build_one(formal, nix_shell, module):
    """Build one check module in its own process group, so the time limit stops Lean and Z3 together."""
    proc = subprocess.Popen(lake(nix_shell, [module]), cwd=formal, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
        return out, False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return out, True


def run_and_parse(formal, base, obligations, nix_shell, jobs):
    """Build the Base module, then every check module in parallel, one verdict per module."""
    proc = subprocess.run(lake(nix_shell, [base]), cwd=formal, capture_output=True, text=True)
    if proc.returncode != 0:
        return None, proc.stdout + proc.stderr
    with ThreadPoolExecutor(max(1, jobs)) as pool:
        outputs = list(pool.map(lambda o: build_one(formal, nix_shell, o["module"]), obligations))
    report, raw = [], proc.stdout + proc.stderr
    for o, (out, timed_out) in zip(obligations, outputs):
        raw += out + (f"\n[stopped after {TIMEOUT} s: {o['module']}]\n" if timed_out else "")
        path = o["module"].replace(".", "/") + ".lean"
        msgs, current = [], False
        for line in out.splitlines():
            m = LOC.search(line)
            if m:
                current = m.group(1).lstrip("./").endswith(path)
                if current:
                    msgs.append(line)
            elif current and line.startswith("  "):
                msgs.append(line)  # a counterexample value printed on its own line
            else:
                current = False
        text = "\n".join(msgs)
        verdict = next((v for marker, v in VERDICTS if marker in text), None)
        if timed_out:
            verdict = "Undetermined"
        elif verdict is None:
            verdict = "Error" if "error" in text else "Unknown"  # no Blaster message: never trust silence
        if verdict == o["expect"]:
            status = "PASS"
        elif verdict in ("Valid", "Falsified"):
            status = "FAIL"
        elif verdict == "Undetermined":
            status = "UNDETERMINED"
        else:
            status = "UNKNOWN"
        witness = parse_witness(msgs, o.get("fields", []))
        report.append({**o, "verdict": "time limit" if timed_out else verdict, "status": status,
                       "witness": ", ".join(witness)})
    return report, raw


def fold_cases(report):
    """One line per check. An existence claim (UP-000, UP-004) holds if one case shows it; a
    universal claim holds only if every reached case does. A case with no accepted spend for its
    action is UNREACHED and proves nothing, so the line names the cases it covers."""
    # Only a proved "always rejects" makes a case unreached; a UP-000 with no verdict decides nothing.
    unreached = {(r["action"], r["case_key"]) for r in report if r["group"].startswith("UP-000") and r["status"] == "FAIL"}
    for r in report:
        if r["status"] == "PASS" and r["expect"] == "Valid" and r["action"] and (r["action"], r["case_key"]) in unreached:
            r["status"] = "UNREACHED"
    groups = {}
    for r in report:
        groups.setdefault(r["group"], []).append(r)
    folded = []
    for gid, rs in groups.items():
        statuses = [x["status"] for x in rs]
        if rs[0]["expect"] == "Falsified":
            pick = next((x for x in rs if x["status"] == "PASS"), None)
            status = "PASS" if pick else ("FAIL" if all(t == "FAIL" for t in statuses) else
                                          next(t for t in statuses if t not in ("PASS", "FAIL")))
        else:
            pick = next((x for x in rs if x["status"] == "FAIL"), None)
            if pick:
                status = "FAIL"
            elif all(t in ("PASS", "UNREACHED") for t in statuses):
                status = "PASS" if "PASS" in statuses else "UNREACHED"
            else:
                status = next(t for t in statuses if t not in ("PASS", "UNREACHED"))
        pick = pick or next((x for x in rs if x["status"] == status), rs[0])
        out = dict(pick, id=gid, status=status)
        if len(rs) > 1:
            out["cases"] = f"{statuses.count('PASS')} of {len(rs)} cases pass" + (
                f", {statuses.count('UNREACHED')} unreached" if "UNREACHED" in statuses else "")
        # A universal claim names every case that fails; an existence claim fails in all of them.
        out["failing"] = [x["case"] for x in rs if x["status"] == "FAIL" and x["case"]] if status == "FAIL" and rs[0]["expect"] == "Valid" else []
        out["stopped"] = [x["module"] for x in rs if x["verdict"] == "time limit"]
        folded.append(out)
    return folded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--formal", default=".")
    ap.add_argument("--config", default="universal.json")
    ap.add_argument("--nix-shell", default=os.environ.get("UNIVERSAL_NIX_SHELL", ""))
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--quick", action="store_true", help="pin every sum type to its first constructor: faster, weaker")
    ap.add_argument("--no-validity", action="store_true", help="drop the ledger-validity hypothesis")
    ap.add_argument("--prep", action="store_true", help="apply the script once with #prep_uplc (fast on small scripts, blows up on vesting)")
    ap.add_argument("--prep-steps", type=int, default=60000, help="CEK step bound for #prep_uplc")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per module, wall clock; a slower module is stopped and reports UNDETERMINED")
    ap.add_argument("--max-cases", type=int, default=16, help="modules per check in full mode; sums that do not fit stay open inside each module")
    ap.add_argument("--jobs", type=int, default=4, help="check modules built in parallel; each runs Lean and Z3, so keep it below the core count")
    ap.add_argument("validators", nargs="+", help="blueprint module names, e.g. vault")
    a = ap.parse_args()
    global NO_VALIDITY, NO_PREP, PREP_STEPS, QUICK, TIMEOUT, MAX_CASES
    NO_VALIDITY, NO_PREP, PREP_STEPS, QUICK, TIMEOUT, MAX_CASES = a.no_validity, not a.prep, a.prep_steps, a.quick, a.timeout, a.max_cases
    formal = Path(a.formal).resolve()
    bp = json.load(open(a.blueprint))
    defs = bp.get("definitions", {})
    cfg = json.load(open(formal / a.config)) if (formal / a.config).exists() else {}
    worst = 0
    today = datetime.date.today().isoformat()

    # Every name is checked before anything runs; a usage error is a run with no verdict (exit 2).
    spends = {}
    for name in a.validators:
        entries = [v for v in bp["validators"] if v["title"].startswith(f"{name}.{name}.")]
        spend = next((v for v in entries if v["title"].endswith(".spend")), None)
        if not entries:
            print(f"no blueprint entry for {name}", file=sys.stderr)
            sys.exit(2)
        if spend is None or spend.get("parameters"):
            print(f"{name}: the prototype covers unparameterised validators with a spend handler", file=sys.stderr)
            sys.exit(2)
        spends[name] = (spend, [h for h in (v["title"].split(".")[-1] for v in entries) if h != "else"])

    for name, (spend, declared) in spends.items():
        gen = DataGen(defs, prefix="d_")
        datum_term = gen.gen(spend["datum"]["schema"], "d") if spend.get("datum") else "Data.I 0"
        # The continuing output's datum has its own leaves and its own choices, so every spend check
        # sees an output whose datum differs from the input's in any way the shape allows.
        out_gen = DataGen(defs, prefix="o_", label="output ")
        out_gen.n = gen.n
        out_datum_term = out_gen.gen(spend["datum"]["schema"], "d") if spend.get("datum") else "Data.I 0"
        in_choices = gen.choices
        gen.binders += out_gen.binders
        gen.n, gen.prefix, gen.label = out_gen.n, "r_", "redeemer "
        variants = gen.variants(spend["redeemer"]["schema"], "r") if spend.get("redeemer") else [("", "Data.I 0", 0, [])]
        mod, base_src, modules, obligations = generate(name, spend["compiledCode"], declared, datum_term, out_datum_term,
                                                       variants, gen.binders, in_choices, out_gen.choices)
        d = formal / "Universal" / "Demo" / mod
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.lean"):
            old.unlink()
        (d / "Base.lean").write_text(base_src)
        for mname, src in modules:
            (d / (mname.split(".")[-1] + ".lean")).write_text(src)
        aggregator = [f"-- Generated by scripts/universal.py: every check for `{name}`. Do not edit; regenerate.",
                      f"-- `lake build Universal.Demo.{mod}` builds them all ({'quick' if QUICK else 'full'} mode)."]
        aggregator += [f"import {mname}" for mname, _ in modules]
        (formal / "Universal" / "Demo" / f"{mod}.lean").write_text("\n".join(aggregator) + "\n")
        n_checks = len({o["group"] for o in obligations})
        print(f"\n== {name}: declared handlers {declared}; {n_checks} checks in {len(obligations)} modules "
              f"-> Universal/Demo/{mod}/ ({'quick mode: sum types pinned to the first constructor' if QUICK else 'full mode'})")
        if a.no_run:
            continue
        print("   PASS holds within the generated shape (see Universal/Notes.lean). HOLE = wrong in almost every contract."
              " REVIEW = can be by design: confirm or waive with a reason. UNREACHED = no accepted spend for this action,"
              " so the check proved nothing. UNDETERMINED = stopped by the time limit. UNKNOWN = Blaster gave no verdict.")
        report, raw = run_and_parse(formal, f"Universal.Demo.{mod}.Base", obligations, a.nix_shell, a.jobs)
        (d / "build.log").write_text(raw)
        if report is None:
            print(f"Universal.Demo.{mod}.Base does not build, so no check ran; see Universal/Demo/{mod}/build.log")
            worst = max(worst, 2)
            continue
        report = fold_cases(report)
        entries = cfg.get(name, {})
        for r in report:
            w = entries.get(r["id"]) or {}
            state = w.get("state", "waived" if w else "")
            expired = state == "waived" and w.get("until", "9999") < today
            status = r["status"]
            if state == "off" or (not r.get("default_on", True) and state != "on"):
                status = "OFF"
            elif state == "waived" and not expired and status == "FAIL":
                status = "WAIVED"
            elif status == "FAIL" and r["severity"] == "review":
                status = "REVIEW"
            label = "HOLE" if status == "FAIL" else status
            print(f"{label:<12} {r['id']:<16} {r['title']}" + (f" ({r['cases']})" if r.get("cases") else ""))
            if status in ("FAIL", "REVIEW"):
                print(f"             consequence: {r['consequence']}")
                for case in r["failing"]:
                    print(f"             fails when: {case}")
            if status in ("FAIL", "REVIEW") or (status == "PASS" and r["expect"] == "Falsified"):
                if r["witness"]:
                    which = "witness" if status == "PASS" else "counterexample" + (" for the first case" if len(r["failing"]) > 1 else "")
                    print(f"             {which}: {r['witness']}")
            if status == "WAIVED":
                who = f" by {w['owner']}" if w.get("owner") else ""
                until = f" until {w['until']}" if w.get("until") else ""
                print(f"             waived{who}{until}, all cases: {w.get('reason', '')}")
            if expired and r["status"] == "FAIL":
                print(f"             the waiver expired on {w['until']}, so it no longer applies")
            if status == "OFF":
                how = "switched off in universal.json" if state == "off" else "off by default; enable it with {\"state\": \"on\"} in universal.json"
                print(f"             {how} (result would be {r['status']})")
            if r["stopped"]:
                print(f"             stopped after {TIMEOUT} s: {', '.join(m.split('.')[-1] for m in r['stopped'])}")
            if status == "UNKNOWN":
                print(f"             blaster said: {r['verdict']}; see Universal/Demo/{mod}/build.log")
            if status == "FAIL":
                worst = max(worst, 1)
            if status in ("UNDETERMINED", "UNREACHED", "UNKNOWN"):
                worst = max(worst, 2)
    sys.exit(worst)


if __name__ == "__main__":
    main()
