#!/usr/bin/env python3
"""Universal-property demo: generate Blaster obligations from a blueprint, run them, report.

The developer supplies only the compiled validator (plutus.json). This script
reads the blueprint, writes one Lean module per validator with the universal
obligations instantiated on that validator, runs `lake build` on it, and prints
a pass/fail report with the waivers from universal.json applied.

The transaction is generic: every list in the script context holds up to two
items and Blaster decides which are present (the "shape" flags); every value is
left open.

Usage, from formal/:
  scripts/universal.py --blueprint ../onchain/plutus.json vault vault_buggy
  scripts/universal.py --blueprint ../onchain/plutus.json --no-run vault   # generate only
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PURPOSES = {
    "mint": ("(.MintingScript cs)", "(cs : ByteString)",
             "anyone could mint or burn tokens under this script's hash"),
    "withdraw": ("(.RewardingScript (.PubKeyCredential h))", "(h : ByteString)",
                 "anyone could withdraw staking rewards held by this script's credential"),
    "publish": ("(.CertifyingScript 0 (.TxCertRegStaking (.PubKeyCredential h) none))", "(h : ByteString)",
                "anyone could publish certificates (delegate, retire) for this credential"),
    "vote": ("(.VotingScript (.DRepVoter (.PubKeyCredential h)))", "(h : ByteString)",
             "anyone could vote with this script as a DRep"),
    "propose": ("(.ProposingScript 0 ⟨0, .PubKeyCredential h, Data.I 0⟩)", "(h : ByteString)",
                "anyone could submit governance proposals guarded by this script"),
}

# The shape flags (Bool) and open values of the generic transaction.
FLAGS = ["in2", "out2", "out1Script", "sig1", "sig2", "mint1", "lowFin"]
BYTES = ["s1", "s2", "payee", "payee2", "policy", "name"]
INTS = ["inLov", "inLov2", "outLov", "outLov2", "qty", "lo", "fee"]


def resolve(ref, defs):
    key = ref.split("/")[-1].replace("~1", "/")
    return defs[key]


class DataGen:
    """Build a Data term with the blueprint's shape and symbolic leaves."""

    def __init__(self, defs):
        self.defs = defs
        self.binders = []  # (name, lean type)
        self.n = 0

    def fresh(self, ty, hint):
        self.n += 1
        name = f"{hint}{self.n}"
        self.binders.append((name, ty))
        return name

    def gen(self, schema, hint="x"):
        if "$ref" in schema:
            key = schema["$ref"].split("/")[-1]
            if key == "Data":
                return "Data.I 0"
            return self.gen(resolve(schema["$ref"], self.defs), hint)
        if "anyOf" in schema:
            return self.gen(schema["anyOf"][0], hint)  # first constructor only (bounded shape)
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
        return "Data.I 0"

    def variants(self, schema, hint):
        """One (name, term) per top-level constructor; a single unnamed term otherwise."""
        if "$ref" in schema and schema["$ref"].split("/")[-1] != "Data":
            schema = resolve(schema["$ref"], self.defs)
        if "anyOf" in schema and all(c.get("dataType") == "constructor" for c in schema["anyOf"]):
            return [(c.get("title") or f"c{c['index']}", self.gen(c, hint)) for c in schema["anyOf"]]
        return [("", self.gen(schema, hint))]


def binders_str(flags=FLAGS, leaves=(), bytes_=BYTES, ints=INTS):
    parts = []
    if flags:
        parts.append(f"({' '.join(flags)} : Bool)")
    parts += [f"({n} : {t})" for n, t in leaves]
    if bytes_:
        parts.append(f"({' '.join(bytes_)} : ByteString)")
    if ints:
        parts.append(f"({' '.join(ints)} : Int)")
    return " ".join(parts)


NO_VALIDITY = False
NO_PREP = True
PREP_STEPS = 60000


def lean_module(name, cbor_path, declared, datum_term, redeemer_variants, leaves):
    """Return (lean source, obligations, module name)."""
    mod = name[0].upper() + name[1:]
    undeclared = [p for p in PURPOSES if p not in declared]
    leaf_args = " ".join(n for n, _ in leaves)
    leaf_binders = " ".join(f"({n} : {t})" for n, t in leaves)
    flag_args = " ".join(FLAGS)
    val_args = " ".join(BYTES + INTS)
    lines = []
    obligations = []

    def emit(s=""):
        lines.append(s)

    def obligation(oid, title, expect, consequence, severity="hole"):
        obligations.append({"id": oid, "title": title, "expect": expect, "severity": severity,
                            "line": len(lines) + 1, "consequence": consequence})

    emit(f"-- Generated by scripts/universal.py from the blueprint entry `{name}`. Do not edit.")
    emit("import Blaster")
    emit("import PlutusCore.UPLC")
    emit("import CardanoLedgerApi.V3")
    emit("import CardanoLedgerApi.V1.Time")
    emit("import PlutusCore.UPLC.PreProcess")
    emit("import Formal.Common")
    emit()
    emit(f"namespace Universal.Demo.{mod}")
    emit()
    emit("open PlutusCore.UPLC.Term (Program)")
    emit("open PlutusCore.ByteString (ByteString)")
    emit("open PlutusCore.Data (Data)")
    emit("open CardanoLedgerApi.IsData.Class (IsData)")
    emit("open CardanoLedgerApi.V3 (Address ScriptContext ScriptInfo TxInfo TxInInfo TxOut Value)")
    emit("open CardanoLedgerApi.V1.Time (POSIXTimeRange lowerBound after everything)")
    emit("open PlutusCore.UPLC.Utils (isSuccessful isUnsuccessful)")
    emit()
    emit(f'#import_uplc importedScript PlutusV3 single_cbor_hex "{cbor_path}"')
    emit("/-- Any script info: the purpose checks call the script for purposes it does not declare. -/")
    emit("def allInputs (ctx : ScriptContext) : List PlutusCore.UPLC.Term.Term := [CardanoLedgerApi.IsData.Class.toTerm ctx]")
    if NO_PREP:
        emit("def validator : Program := importedScript.script")
        emit("def accepts (ctx : ScriptContext) : Prop := Formal.Common.validatorAccepts ctx validator")
        emit("def rejects (ctx : ScriptContext) : Prop := Formal.Common.validatorRejects ctx validator")
    else:
        emit("-- Apply the script to a symbolic context once; every check reuses the prepared result (IOG pattern).")
        emit(f"#prep_uplc prepared importedScript allInputs {PREP_STEPS}")
        emit("def accepts (ctx : ScriptContext) : Prop := isSuccessful (prepared.prop ctx)")
        emit("def rejects (ctx : ScriptContext) : Prop := isUnsuccessful (prepared.prop ctx)")
    if NO_VALIDITY:
        emit("def valid (_ctx : ScriptContext) : Prop := True")
    else:
        emit("/-- Ledger rules (CardanoLedgerApi): the found transactions must be ones the chain would accept. -/")
        emit("def valid (ctx : ScriptContext) : Prop := CardanoLedgerApi.V3.Contexts.validScriptContext ctx = true")
    emit()
    emit('def scriptHash : ByteString := "fake_script_hash_28bytes!!!!"')
    emit("def scriptAddress : Address := ⟨.ScriptCredential scriptHash, none⟩")
    emit("def keyAddress (h : ByteString) : Address := ⟨.PubKeyCredential h, none⟩")
    emit('def ownRef : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 0⟩')
    emit('def ref2 : CardanoLedgerApi.V3.TxOutRef := ⟨"txid_placeholder_32bytes!!!!!!!!", 1⟩')
    emit('def adaOnly (lovelace : Int) : Value := [(Data.B "", Data.Map [(Data.B "", Data.I lovelace)])]')
    emit("def opt {α : Type} (b : Bool) (x : α) : List α := if b then [x] else []")
    emit()
    emit("/-- Datum with the blueprint's shape; the leaves are symbolic. -/")
    emit(f"def datum {leaf_binders} : Data := {datum_term}")
    emit("/-- Redeemers with the blueprint's shape, one per constructor; the leaves are symbolic. -/")
    for rname, rterm in redeemer_variants:
        emit(f"def redeemer{rname} {leaf_binders} : Data := {rterm}")
    typed_redeemer = redeemer_variants[0][0] != ""
    emit()
    emit("/-- Generic transaction: every list holds up to two items; the flags say which are present. -/")
    emit(f"def genTx ({flag_args} : Bool) (d r : Data) ({' '.join(BYTES)} : ByteString) ({' '.join(INTS)} : Int) : TxInfo :=")
    emit("  let in1 : TxInInfo := ⟨ownRef, ⟨scriptAddress, adaOnly inLov, .OutputDatum d, none⟩⟩")
    emit("  let inB : TxInInfo := ⟨ref2, ⟨scriptAddress, adaOnly inLov2, .OutputDatum d, none⟩⟩")
    emit("  let o1 : TxOut := ⟨if out1Script then scriptAddress else keyAddress payee, adaOnly outLov, .OutputDatum d, none⟩")
    emit("  let o2 : TxOut := ⟨keyAddress payee2, adaOnly outLov2, .NoOutputDatum, none⟩")
    emit("  let range : POSIXTimeRange := if lowFin then after lo else everything")
    emit("  { txInfoInputs := [in1] ++ opt in2 inB")
    emit("    txInfoReferenceInputs := []")
    emit("    txInfoOutputs := [o1] ++ opt out2 o2")
    emit("    txInfoFee := fee")
    emit("    txInfoMint := opt mint1 (Data.B policy, Data.Map [(Data.B name, Data.I qty)])")
    emit("    txInfoTxCerts := []")
    emit("    txInfoWdrl := []")
    emit("    txInfoValidRange := IsData.toData range")
    emit("    txInfoSignatories := opt sig1 s1 ++ opt sig2 s2")
    emit("    txInfoRedeemers := [(.Spending ownRef, r)] ++ opt in2 (.Spending ref2, r)")
    emit("    txInfoData := []")
    emit('    txInfoId := "txid_placeholder_32bytes!!!!!!!!"')
    emit("    txInfoVotes := []")
    emit("    txInfoProposalProcedures := []")
    emit("    txInfoCurrentTreasuryAmount := IsData.toData (none : Option Int)")
    emit("    txInfoTreasuryDonation := IsData.toData (none : Option Int) }")
    emit()
    emit("/-- The script spending its own input `ownRef`, inside the generic transaction. -/")
    emit(f"def spendCtx ({flag_args} : Bool) (d r : Data) ({' '.join(BYTES)} : ByteString) ({' '.join(INTS)} : Int) : ScriptContext :=")
    emit(f"  {{ scriptContextTxInfo := genTx {flag_args} d r {val_args}")
    emit("    scriptContextRedeemer := r")
    emit("    scriptContextScriptInfo := .SpendingScript ownRef (some d) }")
    emit()
    emit("/-- The script invoked for a purpose other than spend, inside the generic transaction. -/")
    emit(f"def otherCtx (info : ScriptInfo) ({flag_args} : Bool) (d r : Data) ({' '.join(BYTES)} : ByteString) ({' '.join(INTS)} : Int) : ScriptContext :=")
    emit(f"  {{ scriptContextTxInfo := genTx {flag_args} d r {val_args}")
    emit("    scriptContextRedeemer := r")
    emit("    scriptContextScriptInfo := info }")
    emit()
    all_b = binders_str(FLAGS, leaves)
    r0 = redeemer_variants[0][0]
    ctx_args = f"{flag_args} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}"

    # UP-000 per action: the validator accepts at least one spend (expected Falsified).
    # UP-004 per action: the validator rejects at least one spend (expected Falsified).
    for rname, _ in redeemer_variants:
        tag = f"/{rname}" if rname else ""
        ctx = f"{flag_args} (datum {leaf_args}) (redeemer{rname} {leaf_args}) {val_args}"
        emit(f"/-- UP-000{tag}: is any spend with this action accepted? Blaster must FALSIFY this. -/")
        emit(f"def alwaysRejects{rname} : Prop := ∀ {all_b},")
        emit(f"  valid (spendCtx {ctx}) → rejects (spendCtx {ctx})")
        obligation(f"UP-000{tag}", f"sanity: action `{rname or 'spend'}` is reachable", "Falsified",
                   "no spend of the generated shapes is accepted: funds locked, or a shape is missing")
        emit(f"#blaster (solve-result: 1) [alwaysRejects{rname}]")
        emit()
        emit(f"/-- UP-004{tag}: is any spend with this action rejected? Blaster must FALSIFY this. -/")
        emit(f"def alwaysAccepts{rname} : Prop := ∀ {all_b},")
        emit(f"  valid (spendCtx {ctx}) → accepts (spendCtx {ctx})")
        obligation(f"UP-004{tag}", f"action `{rname or 'spend'}` is not always accepted", "Falsified",
                   "this action accepts every transaction of the generated shapes: an always-true branch")
        emit(f"#blaster (solve-result: 1) [alwaysAccepts{rname}]")
        emit()

    # UP-001 purpose confinement, one theorem per undeclared purpose.
    for p in undeclared:
        info, extra, consequence = PURPOSES[p]
        emit(f"/-- UP-001/{p}: the script declares no `{p}` handler, so it must reject that purpose. -/")
        obligation(f"UP-001/{p}", f"rejects undeclared purpose `{p}`", "Valid", consequence)
        emit(f"theorem up001_{p} {extra} {all_b} :")
        emit(f"    rejects (otherCtx {info} {ctx_args}) := by")
        emit("  blaster")
        emit()

    # UP-002 unauthenticated spend: both signer flags forced off.
    no_sig_flags = " ".join("false" if f in ("sig1", "sig2") else f for f in FLAGS)
    no_sig_b = binders_str([f for f in FLAGS if f not in ("sig1", "sig2")], leaves)
    emit("/-- UP-002: a spend with no signatories is rejected (waive it for permissionless scripts). -/")
    obligation("UP-002", "rejects a spend with no signatories", "Valid",
               "anyone can spend without signing; by design only for permissionless scripts", "review")
    emit(f"theorem up002_unauthenticated_spend {no_sig_b} :")
    emit(f"    valid (spendCtx {no_sig_flags} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) →")
    emit(f"    rejects (spendCtx {no_sig_flags} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) := by")
    emit("  blaster")
    emit()

    # UP-005 malformed redeemer, only when the blueprint gives the redeemer a constructor type.
    if typed_redeemer:
        emit("/-- UP-005: a redeemer of the wrong shape is rejected. -/")
        obligation("UP-005", "rejects a malformed redeemer", "Valid",
                   "a redeemer that matches no declared action is accepted")
        emit(f"theorem up005_malformed_redeemer {all_b} :")
        emit(f"    valid (spendCtx {flag_args} (datum {leaf_args}) (Data.I 0) {val_args}) →")
        emit(f"    rejects (spendCtx {flag_args} (datum {leaf_args}) (Data.I 0) {val_args}) := by")
        emit("  blaster")
        emit()

    # UP-011 datum hijacking: accepted with the output at the script, then moved to a key address.
    at_script = " ".join("true" if f == "out1Script" else f for f in FLAGS)
    moved = " ".join("false" if f == "out1Script" else f for f in FLAGS)
    hij_b = binders_str([f for f in FLAGS if f != "out1Script"], leaves)
    emit("/-- UP-011: a spend accepted with its output back at the script is rejected once that output moves elsewhere. -/")
    obligation("UP-011", "datum hijacking: moving the continuing output is rejected", "Valid",
               "the output the script expects can be sent to another address with the same datum; "
               "by design when paying out is the point, or when nothing is at stake", "review")
    emit(f"theorem up011_datum_hijacking {hij_b} :")
    emit(f"    valid (spendCtx {at_script} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) →")
    emit(f"    valid (spendCtx {moved} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) →")
    emit(f"    accepts (spendCtx {at_script} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) →")
    emit(f"    rejects (spendCtx {moved} (datum {leaf_args}) (redeemer{r0} {leaf_args}) {val_args}) := by")
    emit("  blaster")
    emit()
    emit(f"end Universal.Demo.{mod}")
    return "\n".join(lines) + "\n", obligations, mod


LOC = re.compile(r"([A-Za-z0-9_./-]+\.lean):(\d+):(\d+):")


def run_and_parse(formal, module, obligations, nix_shell):
    cmd = ["lake", "build", module]
    if nix_shell:
        cmd = ["nix", "develop", nix_shell, "-c"] + cmd
    proc = subprocess.run(cmd, cwd=formal, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    # Attribute each message to the nearest preceding obligation line.
    results = {o["id"]: {"messages": []} for o in obligations}
    current = None
    for raw in out.splitlines():
        m = LOC.search(raw)
        if m and module.replace(".", "/") in m.group(1):
            lineno = int(m.group(2))
            current = None
            for o in obligations:
                if o["line"] <= lineno:
                    current = o["id"]
        if current:
            results[current]["messages"].append(raw)
    report = []
    for o in obligations:
        msgs = results[o["id"]]["messages"]
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
            verdict = "Valid" if proc.returncode == 0 or not text else "Unknown"
        status = "PASS" if verdict == o["expect"] else ("FAIL" if verdict in ("Valid", "Falsified") else verdict.upper())
        # Blaster prints the counterexample as `- name: value` lines after "Counterexample:".
        cex_lines = []
        for raw in msgs:
            m = re.search(r":\s*- (\w+): (.*)$", raw)
            if m:
                val = m.group(2).replace("PlutusCore.ByteString.PlutusCore.ByteStringInternal.ByteString.mk ", "")
                cex_lines.append(f"{m.group(1)} = {val}")
        cex = "counterexample: " + ", ".join(cex_lines) if cex_lines else ""
        report.append({**o, "verdict": verdict, "status": status, "counterexample": cex})
    return report, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--formal", default=".")
    ap.add_argument("--config", default="universal.json")
    ap.add_argument("--nix-shell", default=os.environ.get("UNIVERSAL_NIX_SHELL", ""))
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--no-validity", action="store_true", help="drop the ledger-validity hypothesis")
    ap.add_argument("--prep", action="store_true", help="apply the script once with #prep_uplc (fast on small scripts, blows up on vesting)")
    ap.add_argument("--prep-steps", type=int, default=60000, help="CEK step bound for #prep_uplc")
    ap.add_argument("validators", nargs="+", help="blueprint module names, e.g. vault")
    a = ap.parse_args()
    global NO_VALIDITY, NO_PREP, PREP_STEPS
    NO_VALIDITY, NO_PREP, PREP_STEPS = a.no_validity, not a.prep, a.prep_steps
    formal = Path(a.formal).resolve()
    bp = json.load(open(a.blueprint))
    defs = bp.get("definitions", {})
    cfg = json.load(open(formal / a.config)) if (formal / a.config).exists() else {}
    (formal / "Universal" / "Demo" / "Scripts").mkdir(parents=True, exist_ok=True)

    for name in a.validators:
        entries = [v for v in bp["validators"] if v["title"].startswith(f"{name}.{name}.")]
        if not entries:
            sys.exit(f"no blueprint entry for {name}")
        handlers = [v["title"].split(".")[-1] for v in entries]
        declared = [h for h in handlers if h != "else"]
        spend = next((v for v in entries if v["title"].endswith(".spend")), None)
        if spend is None or spend.get("parameters"):
            sys.exit(f"{name}: the demo covers unparameterised validators with a spend handler")
        cbor = formal / "Universal" / "Demo" / "Scripts" / f"{name}.cbor"
        cbor.write_text(spend["compiledCode"])
        gen = DataGen(defs)
        datum_term = gen.gen(spend["datum"]["schema"], "d") if spend.get("datum") else "Data.I 0"
        variants = gen.variants(spend["redeemer"]["schema"], "r") if spend.get("redeemer") else [("", "Data.I 0")]
        src, obligations, mod = lean_module(name, f"Universal/Demo/Scripts/{name}.cbor", declared, datum_term, variants, gen.binders)
        (formal / "Universal" / "Demo" / f"{mod}.lean").write_text(src)
        print(f"\n== {name}: declared handlers {declared}; {len(obligations)} obligations generated "
              f"-> Universal/Demo/{mod}.lean")
        if not a.no_run:
            print("   HOLE = wrong in almost every contract. REVIEW = can be by design: confirm it, or waive it with a reason.")
        if a.no_run:
            continue
        report, raw = run_and_parse(formal, f"Universal.Demo.{mod}", obligations, a.nix_shell)
        (formal / "Universal" / "Demo" / f"{mod}.log").write_text(raw)
        waivers = cfg.get(name, {})
        for r in report:
            w = waivers.get(r["id"])
            status = r["status"]
            if w and status == "FAIL":
                status = "WAIVED"
            elif status == "FAIL" and r["severity"] == "review":
                status = "REVIEW"
            mark = {"PASS": "✅", "FAIL": "❌", "REVIEW": "🔍", "WAIVED": "⚠️ "}.get(status, "❓")
            label = "HOLE" if status == "FAIL" else status
            print(f"{mark} {label:<7} {r['id']:<16} {r['title']}")
            if status in ("FAIL", "REVIEW"):
                print(f"           consequence: {r['consequence']}")
                if r["counterexample"]:
                    print("           " + r["counterexample"])
            if status == "WAIVED":
                print(f"           waived: {w.get('reason', '')}")
            if status not in ("PASS", "FAIL", "WAIVED"):
                print(f"           blaster said: {r['verdict']}")


if __name__ == "__main__":
    main()
