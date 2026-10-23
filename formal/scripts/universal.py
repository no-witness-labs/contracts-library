#!/usr/bin/env python3
"""Universal checks (prototype): generate Blaster obligations from a blueprint, run them, report.

The developer supplies only the compiled validator (plutus.json). This script
reads the blueprint, writes a Base module per validator (the script, the datum
and redeemer shapes, the generic transaction) and one module per check, runs
`lake build` on all the check modules at once so they build in parallel, and
prints a report with the waivers from universal.json applied.

The transaction is generic: every list in the script context that the shape
covers holds up to two items and Blaster decides which are present (the Bool
"shape" flags); every value is open; every sum type in the datum or redeemer
is a Bool-selected choice between its constructors (`--quick` pins each sum to
its first constructor, which is faster and weaker). The ledger rules
(validScriptContext) are a hypothesis on the spend checks. What the shape does
not cover is in Universal/Notes.lean; a PASS holds within the shape.

Usage, from formal/:
  scripts/universal.py --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
  scripts/universal.py --blueprint ../onchain/plutus.json linear_vesting
  scripts/universal.py --blueprint ../onchain/plutus.json --quick linear_vesting
  scripts/universal.py --blueprint ../onchain/plutus.json --no-run linear_vesting   # generate only
Exit code: 1 when any HOLE remains, 2 when any check is UNKNOWN, 0 otherwise.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Each undeclared purpose is tested on a context that carries that purpose's witness
# (the redeemer entry, the withdrawal, the certificate, the vote or the proposal), so a
# fallback keyed on the witness is exercised. The checks are unconditional.
PURPOSES = {
    "mint": {
        "info": "(.MintingScript cs)", "key": "(.Minting cs)", "binders": "(cs : ByteString)",
        "overrides": "txInfoMint := [(Data.B cs, Data.Map [(Data.B name, Data.I qty)])]",
        "consequence": "accepted a mint or burn under this script's hash; if the fallback is meant to handle "
                       "minting, declare the handler, otherwise anyone can mint"},
    "withdraw": {
        "info": "(.RewardingScript (.ScriptCredential h))", "key": "(.Rewarding (.ScriptCredential h))",
        "binders": "(h : ByteString)", "overrides": "txInfoWdrl := [(.ScriptCredential h, 0)]",
        "consequence": "accepted a reward withdrawal for this script's credential; if the fallback is meant to "
                       "handle it, declare the handler, otherwise anyone can take the rewards"},
    "publish": {
        "info": "(.CertifyingScript 0 (.TxCertRegStaking (.ScriptCredential h) none))",
        "key": "(.Certifying 0 (.TxCertRegStaking (.ScriptCredential h) none))", "binders": "(h : ByteString)",
        "overrides": "txInfoTxCerts := [.TxCertRegStaking (.ScriptCredential h) none]",
        "consequence": "accepted a certificate for this script's credential (register, delegate, retire); "
                       "declare the handler or anyone can publish them"},
    "vote": {
        "info": "(.VotingScript (.DRepVoter (.ScriptCredential h)))", "key": "(.Voting (.DRepVoter (.ScriptCredential h)))",
        "binders": "(h : ByteString)", "overrides": "txInfoVotes := [(.DRepVoter (.ScriptCredential h), [])]",
        "consequence": "accepted a vote with this script as a DRep; declare the handler or anyone can vote with it"},
    "propose": {
        "info": "(.ProposingScript 0 ⟨0, .ScriptCredential h, Data.I 0⟩)", "key": "(.Proposing 0 ⟨0, .ScriptCredential h, Data.I 0⟩)",
        "binders": "(h : ByteString)", "overrides": "txInfoProposalProcedures := [⟨0, .ScriptCredential h, Data.I 0⟩]",
        "consequence": "accepted a governance proposal guarded by this script; declare the handler or anyone can propose"},
}

# The shape flags (Bool) and open values of the generic transaction.
FLAGS = ["in2", "out2", "out1Script", "out1Foreign", "sig1", "sig2", "mint1", "lowFin"]
BYTES = ["s1", "s2", "payee", "payee2", "policy", "name"]
INTS = ["inLov", "inLov2", "outLov", "outLov2", "qty", "lo", "fee"]
MIN_LOVELACE = 1_000_000  # realism: no output or input below a plausible min-UTxO

NO_VALIDITY = False
NO_PREP = True
PREP_STEPS = 60000
QUICK = False


def resolve(ref, defs):
    key = ref.split("/")[-1].replace("~1", "/")
    return defs[key]


class DataGen:
    """Build a Data term with the blueprint's shape: symbolic leaves, a Bool choice per sum type."""

    def __init__(self, defs, prefix=""):
        self.defs = defs
        self.prefix = prefix
        self.binders = []  # (name, lean type)
        self.n = 0

    def fresh(self, ty, hint):
        self.n += 1
        name = f"{self.prefix}{hint}{self.n}"
        self.binders.append((name, ty))
        return name

    def gen(self, schema, hint="x"):
        if "$ref" in schema:
            key = schema["$ref"].split("/")[-1]
            if key == "Data":
                return f"Data.I {self.fresh('Int', 'any')}"  # any Data: an open integer stands in
            return self.gen(resolve(schema["$ref"], self.defs), hint)
        if "anyOf" in schema:
            if QUICK:
                return self.gen(schema["anyOf"][0], hint)  # quick mode: first constructor only
            branches = [self.gen(c, hint) for c in schema["anyOf"]]
            term = branches[-1]
            for b in reversed(branches[:-1]):
                flag = self.fresh("Bool", "c")
                term = f"(if {flag} then {b} else {term})"
            return term
        dt = schema.get("dataType")
        if dt == "constructor":
            fields = [self.gen(f, (f.get("title") or hint)[:8]) for f in schema.get("fields", [])]
            return f"Data.Constr {schema['index']} [{', '.join(fields)}]"
        if dt == "bytes":
            return f"Data.B {self.fresh('ByteString', hint)}"
        if dt == "integer":
            return f"Data.I {self.fresh('Int', hint)}"
        if dt == "list":
            if "items" in schema:
                return f"Data.List [{self.gen(schema['items'], hint)}]"  # one element (bounded shape)
            return "Data.List []"
        if dt == "map":
            return "Data.Map []"
        return f"Data.I {self.fresh('Int', 'any')}"

    def variants(self, schema, hint):
        """One (name, term, constructor count) per top-level redeemer constructor; else one unnamed term."""
        if "$ref" in schema and schema["$ref"].split("/")[-1] != "Data":
            schema = resolve(schema["$ref"], self.defs)
        if "anyOf" in schema and all(c.get("dataType") == "constructor" for c in schema["anyOf"]):
            n = len(schema["anyOf"])
            return [(c.get("title") or f"c{c['index']}", self.gen(c, hint), n) for c in schema["anyOf"]]
        return [("", self.gen(schema, hint), 0)]


def binders_str(flags, leaves, bytes_=BYTES, ints=INTS, extra=""):
    parts = []
    if flags:
        parts.append(f"({' '.join(flags)} : Bool)")
    parts += [f"({n} : {t})" for n, t in leaves]
    if bytes_:
        parts.append(f"({' '.join(bytes_)} : ByteString)")
    if ints:
        parts.append(f"({' '.join(ints)} : Int)")
    if extra:
        parts.append(extra)
    return " ".join(parts)


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

- Shape flags: a second script input, a second output, where the first output goes (own script,
  a key, another script), two signers, one minted asset, a finite or absent lower validity bound.
- Every value: lovelace amounts, fee, signers, policy, asset name, quantity, times.
- The datum of the own input, with the blueprint's shape, independent leaves and a Bool choice per
  sum type{' (pinned to the first constructor: quick mode)' if QUICK else ''}; the continuing output's datum has its own open leaves, sums pinned to the first constructor.
- One redeemer per declared action, same treatment; any `Data` leaf is an open integer.

## What is not in the shape

No reference inputs, no withdrawals on spends, no certificates, no datum hashes, no tokens on
inputs, at most two of each list, no finite upper validity bound. A PASS holds within the shape;
a contract whose accept path needs one of these shows UP-000 as REVIEW and its other checks as
UNREACHED. The script hash is a placeholder, used consistently.

## Reading the verdicts

`#blaster (solve-result: 1)` means the stated universal claim must be falsified: the counterexample
is a working transaction Blaster found. A `theorem ... := by blaster` must hold. `valid` is the
ledger rule set from CardanoLedgerApi; `realistic` adds the min-UTxO the model lacks. The purpose
checks are unconditional and carry the purpose's witness. A Blaster `Valid` is an SMT verdict with
no proof term, as everywhere in this repository. One module per check, so lake builds them in
parallel.
-/"""


def generate(name, cbor_path, declared, datum_term, out_datum_term, redeemer_variants, leaves):
    """Return (module name, base source, [(check module name, source)], obligations)."""
    mod = name[0].upper() + name[1:]
    ns = f"Universal.Demo.{mod}"
    # #import_uplc and #prep_uplc declare their name outside any namespace, so two contracts must
    # not share it: a file importing both would fail. Name them after the validator.
    camel = "".join(part[:1].upper() + part[1:] for part in name.split("_"))
    script_id = f"universal{camel}Script"
    prep_id = f"universal{camel}Prepared"
    undeclared = [p for p in PURPOSES if p not in declared]
    leaf_args = " ".join(n for n, _ in leaves)
    leaf_binders = " ".join(f"({n} : {t})" for n, t in leaves)
    flag_args = " ".join(FLAGS)
    val_args = " ".join(BYTES + INTS)
    lean_flags = [f for f in FLAGS if f != "out1Foreign"]
    real = "realistic inLov inLov2 outLov outLov2"

    def spend(flags, rterm, full=False):
        """A spend context. Only UP-011 needs the independent output datum and the foreign-script
        destination; every other check pins them (output datum = input datum, no foreign script) so
        Blaster does not pay for choices the check never uses."""
        od = f"(datumOut {leaf_args})" if full else f"(datum {leaf_args})"
        if not full:
            flags = " ".join("false" if f == "out1Foreign" else f for f in flags.split())
        return f"spendCtx {flags} (datum {leaf_args}) {od} {rterm} {val_args}"

    # ---- Base module: the script, the shapes, the generic transaction ----
    b = []
    b.append(f"-- Generated by scripts/universal.py from the blueprint entry `{name}`. Do not edit; regenerate.")
    b.append("import Blaster")
    b.append("import PlutusCore.UPLC")
    b.append("import CardanoLedgerApi.V3")
    b.append("import CardanoLedgerApi.V1.Time")
    b.append("import PlutusCore.UPLC.PreProcess")
    b.append("import Formal.Common")
    b.append("")
    b.append(header_notes(name))
    b.append("")
    b.append(f"namespace {ns}")
    b.append("")
    b += OPENS
    b.append("")
    b.append(f'#import_uplc {script_id} PlutusV3 single_cbor_hex "{cbor_path}"')
    if NO_PREP:
        b.append(f"def validator : Program := {script_id}.script")
        b.append("def accepts (ctx : ScriptContext) : Prop := Formal.Common.validatorAccepts ctx validator")
        b.append("def rejects (ctx : ScriptContext) : Prop := Formal.Common.validatorRejects ctx validator")
    else:
        b.append("def allInputs (ctx : ScriptContext) : List PlutusCore.UPLC.Term.Term := [CardanoLedgerApi.IsData.Class.toTerm ctx]")
        b.append(f"#prep_uplc {prep_id} {script_id} allInputs {PREP_STEPS}")
        b.append(f"def accepts (ctx : ScriptContext) : Prop := isSuccessful ({prep_id}.prop ctx)")
        b.append(f"def rejects (ctx : ScriptContext) : Prop := isUnsuccessful ({prep_id}.prop ctx)")
    if NO_VALIDITY:
        b.append("def valid (_ctx : ScriptContext) : Prop := True")
    else:
        b.append("/-- Ledger rules (CardanoLedgerApi): a counterexample must be a transaction the chain would accept. -/")
        b.append("def valid (ctx : ScriptContext) : Prop := CardanoLedgerApi.V3.Contexts.validScriptContext ctx = true")
    b.append("/-- Realism the ledger model does not enforce: no value below a plausible min-UTxO. -/")
    b.append("def realistic (inLov inLov2 outLov outLov2 : Int) : Prop :=")
    b.append(f"  {MIN_LOVELACE} ≤ inLov ∧ {MIN_LOVELACE} ≤ inLov2 ∧ {MIN_LOVELACE} ≤ outLov ∧ {MIN_LOVELACE} ≤ outLov2")
    b.append("")
    b.append('def scriptHash : ByteString := "fake_script_hash_28bytes!!!!"')
    b.append("def scriptAddress : Address := ⟨.ScriptCredential scriptHash, none⟩")
    b.append("def keyAddress (h : ByteString) : Address := ⟨.PubKeyCredential h, none⟩")
    b.append("def foreignScriptAddress (h : ByteString) : Address := ⟨.ScriptCredential h, none⟩")
    b.append('def ownRef : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 0⟩')
    b.append('def ref2 : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 1⟩')
    b.append('def adaOnly (lovelace : Int) : Value := [(Data.B "", Data.Map [(Data.B "", Data.I lovelace)])]')
    b.append("def opt {α : Type} (b : Bool) (x : α) : List α := if b then [x] else []")
    b.append("")
    b.append("/-- Datum of the script's own input, with the blueprint's shape; leaves symbolic, sums chosen by Bool flags. -/")
    b.append(f"def datum {leaf_binders} : Data := {datum_term}")
    b.append("/-- Datum of the continuing output: same shape, independent leaves, so it may differ from the input's. -/")
    b.append(f"def datumOut {leaf_binders} : Data := {out_datum_term}")
    b.append("/-- Redeemers with the blueprint's shape, one per constructor; leaves symbolic. -/")
    for rname, rterm, _ in redeemer_variants:
        b.append(f"def redeemer{rname} {leaf_binders} : Data := {rterm}")
    b.append("")
    b.append("/-- Generic transaction: every covered list holds up to two items; the flags say which are present. -/")
    b.append(f"def genTx ({flag_args} : Bool) (d od r : Data) ({' '.join(BYTES)} : ByteString) ({' '.join(INTS)} : Int) : TxInfo :=")
    b.append("  let in1 : TxInInfo := ⟨ownRef, ⟨scriptAddress, adaOnly inLov, .OutputDatum d, none⟩⟩")
    b.append("  let inB : TxInInfo := ⟨ref2, ⟨scriptAddress, adaOnly inLov2, .OutputDatum d, none⟩⟩")
    b.append("  let minted := opt mint1 (Data.B policy, Data.Map [(Data.B name, Data.I qty)])")
    b.append("  let dest1 : Address := if out1Script then scriptAddress else if out1Foreign then foreignScriptAddress payee else keyAddress payee")
    b.append("  let o1 : TxOut := ⟨dest1, adaOnly outLov ++ minted, .OutputDatum od, none⟩")
    b.append("  let o2 : TxOut := ⟨keyAddress payee2, adaOnly outLov2, .NoOutputDatum, none⟩")
    b.append("  let range : POSIXTimeRange := if lowFin then after lo else everything")
    b.append("  { txInfoInputs := [in1] ++ opt in2 inB")
    b.append("    txInfoReferenceInputs := []")
    b.append("    txInfoOutputs := [o1] ++ opt out2 o2")
    b.append("    txInfoFee := fee")
    b.append("    txInfoMint := minted")
    b.append("    txInfoTxCerts := []")
    b.append("    txInfoWdrl := []")
    b.append("    txInfoValidRange := IsData.toData range")
    b.append("    txInfoSignatories := opt sig1 s1 ++ opt sig2 s2")
    b.append("    txInfoRedeemers := [(.Spending ownRef, r)] ++ opt in2 (.Spending ref2, r)")
    b.append("    txInfoData := []")
    b.append('    txInfoId := "txid_placeholder_32bytes!!!!!!!!"')
    b.append("    txInfoVotes := []")
    b.append("    txInfoProposalProcedures := []")
    b.append("    txInfoCurrentTreasuryAmount := IsData.toData (none : Option Int)")
    b.append("    txInfoTreasuryDonation := IsData.toData (none : Option Int) }")
    b.append("")
    b.append("/-- The script spending its own input `ownRef`, inside the generic transaction. -/")
    b.append(f"def spendCtx ({flag_args} : Bool) (d od r : Data) ({' '.join(BYTES)} : ByteString) ({' '.join(INTS)} : Int) : ScriptContext :=")
    b.append(f"  {{ scriptContextTxInfo := genTx {flag_args} d od r {val_args}")
    b.append("    scriptContextRedeemer := r")
    b.append("    scriptContextScriptInfo := .SpendingScript ownRef (some d) }")
    b.append("")
    b.append("/-- The script invoked for another purpose: the purpose's witness and redeemer entry are added to the transaction. -/")
    b.append("def otherCtx (info : ScriptInfo) (key : ScriptPurpose) (rp : Data) (tx : TxInfo) : ScriptContext :=")
    b.append("  { scriptContextTxInfo := { tx with txInfoRedeemers := (key, rp) :: tx.txInfoRedeemers }")
    b.append("    scriptContextRedeemer := rp")
    b.append("    scriptContextScriptInfo := info }")
    b.append("")
    b.append(f"end {ns}")
    base_src = "\n".join(b) + "\n"

    # ---- One module per check ----
    modules = []
    obligations = []

    def check(mod_name, oid, title, expect, consequence, severity, action, body, default_on=True):
        lines = [f"-- Generated by scripts/universal.py: {oid} for `{name}`. Do not edit; regenerate.",
                 f"import {ns}.Base", "", f"namespace {ns}", ""] + OPENS + [""] + body + ["", f"end {ns}"]
        modules.append((f"{ns}.{mod_name}", "\n".join(lines) + "\n"))
        obligations.append({"id": oid, "module": f"{ns}.{mod_name}", "title": title, "expect": expect,
                            "severity": severity, "action": action, "default_on": default_on,
                            "consequence": consequence})

    all_b = binders_str(FLAGS, leaves)
    lean_b = binders_str(lean_flags, leaves)
    typed_redeemer = redeemer_variants[0][0] != ""
    n_ctors = redeemer_variants[0][2]

    for rname, _, _ in redeemer_variants:
        tag = f"/{rname}" if rname else ""
        act = rname or "spend"
        rterm = f"(redeemer{rname} {leaf_args})"
        ctx = spend(flag_args, rterm)
        check(f"UP000_{act}", f"UP-000{tag}", f"sanity: action `{act}` is reachable", "Falsified",
              "no spend of the generated shapes is accepted: funds locked, or the action needs something the "
              "shape lacks (reference inputs, withdrawals, tokens on inputs, a third output)", "review", act, [
                  f"/-- UP-000{tag}: is any realistic valid spend with this action accepted? Blaster must FALSIFY this. -/",
                  f"def alwaysRejects{rname} : Prop := ∀ {lean_b},",
                  f"  valid ({ctx}) → {real} → rejects ({ctx})",
                  f"#blaster (solve-result: 1) [alwaysRejects{rname}]"])
        check(f"UP004_{act}", f"UP-004{tag}", f"action `{act}` is not always accepted", "Falsified",
              "this action accepts every realistic valid transaction of the generated shapes: an always-true branch",
              "hole", act, [
                  f"/-- UP-004{tag}: is any realistic valid spend with this action rejected? Blaster must FALSIFY this. -/",
                  f"def alwaysAccepts{rname} : Prop := ∀ {lean_b},",
                  f"  valid ({ctx}) → {real} → accepts ({ctx})",
                  f"#blaster (solve-result: 1) [alwaysAccepts{rname}]"])
        no_sig_flags = " ".join("false" if f in ("sig1", "sig2") else f for f in FLAGS)
        no_sig_b = binders_str([f for f in lean_flags if f not in ("sig1", "sig2")], leaves)
        ctx_ns = spend(no_sig_flags, rterm)
        check(f"UP002_{act}", f"UP-002{tag}", f"action `{act}` rejects a spend with no signatories", "Valid",
              "this action can be spent without any signature; by design only for scripts authenticated another way",
              "review", act, [
                  f"/-- UP-002{tag}: a realistic valid spend with no signatories is rejected (waive it for permissionless scripts). -/",
                  f"theorem up002_{act} {no_sig_b} :",
                  f"    valid ({ctx_ns}) → {real} → rejects ({ctx_ns}) := by",
                  "  blaster"])
        at_script = " ".join("true" if f == "out1Script" else f for f in FLAGS)
        moved = " ".join("false" if f == "out1Script" else f for f in FLAGS)
        hij_b = binders_str([f for f in FLAGS if f != "out1Script"], leaves)
        check(f"UP011_{act}", f"UP-011{tag}", f"action `{act}`: moving the continuing output is rejected", "Valid",
              "the same spend was accepted with the output moved elsewhere; confirm that paying out is intended "
              "for this action and this case, otherwise the datum can be hijacked", "review", act, [
                  f"/-- UP-011{tag}: a spend accepted with its output (any datum) back at the script is rejected once that output moves to a key or foreign script address. -/",
                  f"theorem up011_{act} {hij_b} :",
                  f"    valid ({spend(at_script, rterm, True)}) → valid ({spend(moved, rterm, True)}) → {real} →",
                  f"    accepts ({spend(at_script, rterm, True)}) → rejects ({spend(moved, rterm, True)}) := by",
                  "  blaster"])

    if typed_redeemer:
        check("UP005", "UP-005", "rejects a malformed redeemer", "Valid",
              "a redeemer that matches no declared action is accepted", "hole", "", [
                  "/-- UP-005: a realistic valid spend with a redeemer of the wrong shape is rejected: any integer, or any constructor the type lacks. -/",
                  f"theorem up005_integer_redeemer {binders_str(lean_flags, leaves, extra='(m : Int)')} :",
                  f"    valid ({spend(flag_args, '(Data.I m)')}) → {real} → rejects ({spend(flag_args, '(Data.I m)')}) := by",
                  "  blaster",
                  f"theorem up005_unknown_constructor {binders_str(lean_flags, leaves, extra=f'(k : Nat) (hk : {n_ctors} ≤ k)')} :",
                  f"    valid ({spend(flag_args, '(Data.Constr k [])')}) → {real} → rejects ({spend(flag_args, '(Data.Constr k [])')}) := by",
                  "  blaster"])

    for p in undeclared:
        spec = PURPOSES[p]
        check(f"UP001_{p}", f"UP-001/{p}", f"rejects undeclared purpose `{p}`", "Valid", spec["consequence"], "hole", "", [
            f"/-- UP-001/{p}: the script declares no `{p}` handler, so it must reject that purpose, even with the purpose's witness present. -/",
            f"theorem up001_{p} {spec['binders']} {binders_str(FLAGS, leaves, extra='(rp : Int)')} :",
            f"    rejects (otherCtx {spec['info']} {spec['key']} (Data.I rp)",
            f"      {{ genTx {flag_args} (datum {leaf_args}) (datumOut {leaf_args}) (Data.I rp) {val_args} with {spec['overrides']} }}) := by",
            "  blaster"])
    # UP-013 unbounded validity range: off by default, only time-based scripts need it.
    r0 = redeemer_variants[0][0]
    rterm0 = f"(redeemer{r0} {leaf_args})"
    unbounded = " ".join("false" if f == "lowFin" else f for f in FLAGS)
    unb_b = binders_str([f for f in lean_flags if f != "lowFin"], leaves)
    check("UP013", "UP-013", "rejects a spend with an unbounded validity range", "Valid",
          "a time check passes on a range with no start; enable this check for time-based scripts",
          "review", r0 or "spend", [
              "/-- UP-013: a realistic valid spend whose validity range has no lower bound is rejected. Off by default. -/",
              f"theorem up013_unbounded_validity_range {unb_b} :",
              f"    valid ({spend(unbounded, rterm0)}) → {real} → rejects ({spend(unbounded, rterm0)}) := by",
              "  blaster"], default_on=False)
    return mod, base_src, modules, obligations


LOC = re.compile(r"([A-Za-z0-9_./-]+\.lean):(\d+):(\d+):")


def run_and_parse(formal, obligations, nix_shell, jobs):
    """Build every check module in one lake call (parallel), attribute messages by file."""
    # lake builds every requested module concurrently and has no jobs flag here, so the modules
    # go in batches of `jobs`: each batch runs in parallel, the batches one after another.
    mods = [o["module"] for o in obligations]
    out, rc = "", 0
    for i in range(0, len(mods), max(1, jobs)):
        cmd = ["lake", "build"] + mods[i:i + max(1, jobs)]
        if nix_shell:
            cmd = ["nix", "develop", nix_shell, "-c"] + cmd
        proc = subprocess.run(cmd, cwd=formal, capture_output=True, text=True)
        out += proc.stdout + proc.stderr
        rc = max(rc, proc.returncode)
    by_file = {o["module"].replace(".", "/") + ".lean": o["id"] for o in obligations}
    results = {o["id"]: [] for o in obligations}
    for raw in out.splitlines():
        m = LOC.search(raw)
        if m:
            path = m.group(1).lstrip("./")
            for f, oid in by_file.items():
                if path.endswith(f):
                    results[oid].append(raw)
    report = []
    for o in obligations:
        msgs = results[o["id"]]
        text = "\n".join(msgs)
        if "Falsified" in text:
            verdict = "Falsified"
        elif "Valid" in text:
            verdict = "Valid"
        elif "Undetermined" in text or "timeout" in text.lower():
            verdict = "Undetermined"
        elif "error" in text:
            verdict = "Error"
        else:
            verdict = "Unknown"  # no Blaster message for this check: never trust silence
        if verdict == o["expect"]:
            status = "PASS"
        elif verdict in ("Valid", "Falsified"):
            status = "FAIL"
        else:
            status = "UNKNOWN"
        witness = []
        for raw in msgs:
            m = re.search(r":\s*- (\w+): (.*)$", raw)
            if m:
                val = m.group(2).replace("PlutusCore.ByteString.PlutusCore.ByteStringInternal.ByteString.mk ", "")
                witness.append(f"{m.group(1)} = {val}")
        report.append({**o, "verdict": verdict, "status": status, "witness": ", ".join(witness)})
    return report, out, rc


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
    ap.add_argument("--jobs", type=int, default=4, help="check modules built in parallel; each runs Lean and Z3, so keep it below the core count")
    ap.add_argument("validators", nargs="+", help="blueprint module names, e.g. vault")
    a = ap.parse_args()
    global NO_VALIDITY, NO_PREP, PREP_STEPS, QUICK
    NO_VALIDITY, NO_PREP, PREP_STEPS, QUICK = a.no_validity, not a.prep, a.prep_steps, a.quick
    formal = Path(a.formal).resolve()
    bp = json.load(open(a.blueprint))
    defs = bp.get("definitions", {})
    cfg = json.load(open(formal / a.config)) if (formal / a.config).exists() else {}
    (formal / "Universal" / "Demo" / "Scripts").mkdir(parents=True, exist_ok=True)
    worst = 0

    for name in a.validators:
        entries = [v for v in bp["validators"] if v["title"].startswith(f"{name}.{name}.")]
        if not entries:
            sys.exit(f"no blueprint entry for {name}")
        handlers = [v["title"].split(".")[-1] for v in entries]
        declared = [h for h in handlers if h != "else"]
        spend = next((v for v in entries if v["title"].endswith(".spend")), None)
        if spend is None or spend.get("parameters"):
            sys.exit(f"{name}: the prototype covers unparameterised validators with a spend handler")
        cbor = formal / "Universal" / "Demo" / "Scripts" / f"{name}.cbor"
        cbor.write_text(spend["compiledCode"])
        gen = DataGen(defs)
        datum_term = gen.gen(spend["datum"]["schema"], "d") if spend.get("datum") else "Data.I 0"
        # The continuing output's datum keeps its leaves open but pins its sum types to the first
        # constructor even in full mode: UP-011 is the only user, and the extra choices made it the
        # one check that did not finish on vesting.
        out_gen = DataGen(defs, prefix="o_")
        out_gen.n = gen.n
        quick_before, QUICK = QUICK, True
        out_datum_term = out_gen.gen(spend["datum"]["schema"], "d") if spend.get("datum") else "Data.I 0"
        QUICK = quick_before
        gen.binders += out_gen.binders
        gen.n = out_gen.n
        variants = gen.variants(spend["redeemer"]["schema"], "r") if spend.get("redeemer") else [("", "Data.I 0", 0)]
        mod, base_src, modules, obligations = generate(name, f"Universal/Demo/Scripts/{name}.cbor", declared,
                                                       datum_term, out_datum_term, variants, gen.binders)
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
        print(f"\n== {name}: declared handlers {declared}; {len(obligations)} checks generated "
              f"-> Universal/Demo/{mod}/ ({'quick mode: sum types pinned to the first constructor' if QUICK else 'full mode'})")
        if a.no_run:
            continue
        print("   PASS holds within the generated shape (see Universal/Notes.lean). HOLE = wrong in almost every contract."
              " REVIEW = can be by design: confirm or waive with a reason. UNREACHED = no accepted spend for this action,"
              " so the check proved nothing. UNKNOWN = Blaster gave no verdict.")
        report, raw, rc = run_and_parse(formal, obligations, a.nix_shell, a.jobs)
        (d / "build.log").write_text(raw)
        unreached = {r["action"] for r in report if r["id"].startswith("UP-000") and r["status"] != "PASS"}
        waivers = cfg.get(name, {})
        for r in report:
            w = waivers.get(r["id"])
            status = r["status"]
            if not r.get("default_on", True) and not (w and w.get("state") == "on"):
                status = "OFF"
            elif status == "PASS" and r["expect"] == "Valid" and r["action"] in unreached:
                status = "UNREACHED"
            elif w and status == "FAIL":
                status = "WAIVED"
            elif status == "FAIL" and r["severity"] == "review":
                status = "REVIEW"
            label = "HOLE" if status == "FAIL" else status
            print(f"{label:<9} {r['id']:<16} {r['title']}")
            if status in ("FAIL", "REVIEW"):
                print(f"          consequence: {r['consequence']}")
            if status in ("FAIL", "REVIEW") or (status == "PASS" and r["expect"] == "Falsified"):
                if r["witness"]:
                    print(f"          {'witness' if status == 'PASS' else 'counterexample'}: {r['witness']}")
            if status == "WAIVED":
                who = f" by {w['owner']}" if w.get("owner") else ""
                until = f" until {w['until']}" if w.get("until") else ""
                print(f"          waived{who}{until}: {w.get('reason', '')}")
            if status == "OFF":
                print(f"          off by default; enable it with {{\"state\": \"on\"}} in universal.json (result would be {r['status']})")
            if status == "UNKNOWN":
                print(f"          blaster said: {r['verdict']}; lake exit code {rc}")
            if status == "FAIL":
                worst = max(worst, 1)
            if status == "UNKNOWN":
                worst = max(worst, 2)
    sys.exit(worst)


if __name__ == "__main__":
    main()
