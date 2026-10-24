#!/usr/bin/env python3
"""Turn one validator of an Aiken blueprint (plutus.json) into Lean, in two passes.

Usage, from formal/ (or with `just blueprint <validator>`):
  scripts/process_blueprint.py ../onchain/plutus.json linear_vesting
  scripts/process_blueprint.py ../onchain/plutus.json dao/stake.stake
  scripts/process_blueprint.py ../onchain/plutus.json linear_vesting --no-checks

Writes <out>/<Validator>.lean and <scripts>/<module>.<name>.cbor (the blueprint's compiledCode).

Pass 1, extract: types, IsData instances, parameters, arguments and the script, plus a
  ValidatorInfo, which is the only input of pass 2.
Pass 2, checks: appended to the same file. The G checks (G1-G2) are proved by Blaster over every
  transaction; the H checks (H1-H19) are on honest transactions and stay `sorry` until those are
  written. `--no-checks` skips pass 2.

The validator is named `module.validator` as in the blueprint titles, or just `validator`
when that is unambiguous. Every schema form is translated as described in TRANSLATION below;
an unknown form stops the run with the definition's name.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TRANSLATION = """
Schema form                         Lean type              Encoding
integer                             Int                    Data.I
bytes (ByteArray, hashes, ids)      ByteString             Data.B
Data, or an empty schema            Data                   as is
list with `items: T`                List T                 Data.List
list with `items: [T1, ..]`         T1 × .. (a tuple)      Data.List [..]
map with keys K, values V           List (K × V)           Data.Map
Option<T>                           Option T               Some = Constr 0 [x], None = Constr 1 []
Bool                                Bool                   False = Constr 0 [], True = Constr 1 []
cardano/address/Credential          Credential             (CardanoLedgerApi.V3)
cardano/address/StakeCredential     StakingCredential      (CardanoLedgerApi.V3)
cardano/address/Address             Address                (CardanoLedgerApi.V3)
cardano/transaction/OutputReference TxOutRef               (CardanoLedgerApi.V3)
one constructor                     structure              Constr index [fields]
several constructors                inductive              Constr index [fields]
a definition that refers to itself  Data                   as is (a warning comment is written)
"""

# Lean keywords and names that cannot be used as field or constructor names.
LEAN_RESERVED = {
    "abbrev", "at", "attribute", "axiom", "break", "by", "calc", "catch", "class", "continue",
    "decreasing_by", "def", "deriving", "do", "else", "end", "example", "exists", "extends",
    "finally", "for", "forall", "from", "fun", "have", "if", "import", "in", "inductive",
    "instance", "let", "local", "macro", "match", "mk", "mut", "mutual", "namespace",
    "noncomputable", "nomatch", "nofun", "notation", "opaque", "open", "partial", "private",
    "protected", "rec", "return", "section", "set_option", "show", "sorry", "structure",
    "syntax", "termination_by", "then", "theorem", "try", "universe", "unless", "unsafe",
    "variable", "where", "with", "Prop", "Sort", "Type",
}

# Cardano types reused from CardanoLedgerApi.V3, with the constructor layout their IsData
# instances use. A mapping applies only when the blueprint's schema has exactly this layout
# (index and arity of every constructor); otherwise the type is generated from its schema.
LEDGER_TYPES = {
    "cardano/address/Credential": ("Credential", [(0, 1), (1, 1)]),
    "cardano/address/StakeCredential": ("StakingCredential", [(0, 1), (1, 3)]),
    "cardano/address/Address": ("Address", [(0, 2)]),
    "cardano/transaction/OutputReference": ("TxOutRef", [(0, 2)]),
}


class ExtractError(Exception):
    pass


def camel(segment):
    """`poll_effect` -> `PollEffect`, `types` -> `Types`; other characters are dropped."""
    parts = re.split(r"[^A-Za-z0-9]+", segment)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def ident(name, fallback):
    """A Lean identifier for a field or constructor title; reserved words are «quoted»."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", name or "") or fallback
    if s[0].isdigit():
        s = "_" + s
    return f"«{s}»" if s in LEAN_RESERVED else s


class Translator:
    def __init__(self, definitions):
        self.defs = definitions
        self.named = {}       # definition key -> Lean type name, for generated types
        self.order = []       # definition keys, dependencies first
        self.decls = {}       # definition key -> (kind, constructors)
        self.visiting = []    # keys being translated (cycle detection)
        self.warnings = []

    # ---- schema resolution ----

    def resolve(self, schema):
        """Return (key, schema) with `$ref` followed; key is None for inline schemas."""
        if "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/definitions/"):
                raise ExtractError(f"unsupported reference {ref}")
            key = ref[len("#/definitions/"):].replace("~1", "/").replace("~0", "~")
            if key not in self.defs:
                raise ExtractError(f"missing definition {key}")
            return key, self.defs[key]
        return None, schema

    # ---- types ----

    def ty(self, schema, where):
        """Translate a schema into a type description used by `lean_type`, `enc` and `dec`."""
        key, s = self.resolve(schema)
        if key in LEDGER_TYPES and self.ledger_layout_matches(s, LEDGER_TYPES[key][1]):
            return ("ledger", LEDGER_TYPES[key][0])
        if key is not None and key in self.visiting:
            self.warnings.append(f"{key} refers to itself; translated as Data in {where}")
            return ("data",)
        if "anyOf" in s:
            ctors = s["anyOf"]
            if self.is_option(key, ctors):
                return ("option", self.ty(ctors[0]["fields"][0], where))
            if self.is_bool(key, ctors):
                return ("bool",)
            return ("named", self.declare(key, s, where))
        dt = s.get("dataType")
        if dt is None:
            if set(s) - {"title", "description", "$comment"}:
                raise ExtractError(f"unknown schema form in {where}: {json.dumps(s)[:200]}")
            return ("data",)
        if dt == "integer":
            return ("int",)
        if dt == "bytes":
            return ("bytes",)
        if dt == "list":
            items = s.get("items")
            if isinstance(items, list):
                return ("tuple", [self.ty(i, where) for i in items])
            if items is None:
                return ("list", ("data",))
            return ("list", self.ty(items, where))
        if dt == "map":
            k = self.ty(s["keys"], where) if "keys" in s else ("data",)
            v = self.ty(s["values"], where) if "values" in s else ("data",)
            return ("map", k, v)
        if dt == "constructor":
            return ("named", self.declare(key, {"anyOf": [s]}, where))
        raise ExtractError(f"unknown dataType {dt!r} in {where}")

    @staticmethod
    def ledger_layout_matches(s, layout):
        ctors = s.get("anyOf")
        if not ctors:
            return False
        got = sorted((c.get("index"), len(c.get("fields", []))) for c in ctors)
        return got == sorted(layout)

    @staticmethod
    def is_option(key, ctors):
        return (key or "").startswith("Option<") and len(ctors) == 2 \
            and ctors[0].get("index") == 0 and len(ctors[0].get("fields", [])) == 1 \
            and ctors[1].get("index") == 1 and not ctors[1].get("fields")

    @staticmethod
    def is_bool(key, ctors):
        return key == "Bool" and [(c.get("index"), len(c.get("fields", []))) for c in ctors] == [(0, 0), (1, 0)]

    def lean_name(self, key):
        """`vesting/types/VestingDatum` -> `Vesting.Types.VestingDatum`; generics become suffixes."""
        base, _, generic = key.partition("<")
        segs = [camel(p) for p in base.split("/")]
        if generic:
            segs[-1] += "_" + camel(generic.rstrip(">"))
        if len(segs) == 1:
            segs.insert(0, "Types")
        return ".".join(segs)

    def declare(self, key, s, where):
        if key is None:
            raise ExtractError(f"inline constructor type in {where}; only named ones are supported")
        if key in self.named:
            return self.named[key]
        name = self.lean_name(key)
        self.visiting.append(key)
        ctors = []
        for i, c in enumerate(s["anyOf"]):
            if c.get("dataType") != "constructor":
                raise ExtractError(f"non-constructor alternative in {key}")
            fields = []
            for j, f in enumerate(c.get("fields", [])):
                fields.append((ident(f.get("title"), f"field{j}"), self.ty(f, f"{key}.{f.get('title', j)}")))
            ctor_name = ident(c.get("title"), f"Ctor{i}")
            ctors.append((ctor_name, c["index"], fields))
        self.visiting.pop()
        kind = "structure" if len(ctors) == 1 else "inductive"
        if name in self.named.values():
            raise ExtractError(f"two definitions translate to the Lean name {name}")
        self.named[key] = name
        self.decls[key] = (kind, ctors)
        self.order.append(key)
        return name


# ---- Lean text ----

def lean_type(t):
    tag = t[0]
    if tag == "int":
        return "Int"
    if tag == "bytes":
        return "ByteString"
    if tag == "data":
        return "Data"
    if tag == "bool":
        return "Bool"
    if tag in ("ledger", "named"):
        return t[1]
    if tag == "list":
        return f"List ({lean_type(t[1])})"
    if tag == "map":
        return f"List ({lean_type(t[1])} × {lean_type(t[2])})"
    if tag == "option":
        return f"Option ({lean_type(t[1])})"
    if tag == "tuple":
        return "(" + " × ".join(lean_type(x) for x in t[1]) + ")"
    raise AssertionError(t)


class Fresh:
    def __init__(self):
        self.n = 0

    def __call__(self, base="v"):
        self.n += 1
        return f"{base}{self.n}"


def tuple_proj(e, i, n):
    """Projection `e.2.2.1` of component i of an n-tuple (Lean products nest to the right)."""
    if n == 1:
        return e
    path = ".2" * i + (".1" if i < n - 1 else "")
    return f"({e}){path}"


def enc(t, e, fresh):
    """A Lean expression of type Data encoding `e : lean_type t`."""
    tag = t[0]
    if tag == "int":
        return f"Data.I {e}"
    if tag == "bytes":
        return f"Data.B {e}"
    if tag == "data":
        return e
    if tag in ("ledger", "named"):
        return f"IsData.toData {e}"
    if tag == "bool":
        return f"(if {e} then Data.Constr 1 [] else Data.Constr 0 [])"
    if tag == "option":
        v = fresh()
        return f"(match {e} with | some {v} => Data.Constr 0 [{enc(t[1], v, fresh)}] | none => Data.Constr 1 [])"
    if tag == "list":
        v = fresh()
        return f"Data.List (({e}).map (fun {v} => {enc(t[1], v, fresh)}))"
    if tag == "map":
        v = fresh()
        return f"Data.Map (({e}).map (fun {v} => ({enc(t[1], v + '.1', fresh)}, {enc(t[2], v + '.2', fresh)})))"
    if tag == "tuple":
        n = len(t[1])
        return "Data.List [" + ", ".join(enc(x, tuple_proj(e, i, n), fresh) for i, x in enumerate(t[1])) + "]"
    raise AssertionError(t)


def dec(t, d, fresh):
    """A Lean expression of type Option (lean_type t) decoding `d : Data`."""
    tag = t[0]
    if tag == "int":
        v = fresh("i")
        return f"(match {d} with | Data.I {v} => some {v} | _ => none)"
    if tag == "bytes":
        v = fresh("b")
        return f"(match {d} with | Data.B {v} => some {v} | _ => none)"
    if tag == "data":
        return f"(some {d})"
    if tag in ("ledger", "named"):
        return f"(IsData.fromData {d} : Option {t[1]})"
    if tag == "bool":
        return (f"(match {d} with | Data.Constr 0 [] => some false "
                f"| Data.Constr 1 [] => some true | _ => none)")
    if tag == "option":
        v = fresh()
        return (f"(match {d} with | Data.Constr 0 [{v}] => ({dec(t[1], v, fresh)}).map some "
                f"| Data.Constr 1 [] => some none | _ => none)")
    if tag == "list":
        v, xs = fresh(), fresh("xs")
        return f"(match {d} with | Data.List {xs} => {xs}.mapM (fun {v} => {dec(t[1], v, fresh)}) | _ => none)"
    if tag == "map":
        p, ps, k, w = fresh("p"), fresh("ps"), fresh("k"), fresh("w")
        return (f"(match {d} with | Data.Map {ps} => {ps}.mapM (fun {p} => do "
                f"let {k} ← {dec(t[1], p + '.1', fresh)}; let {w} ← {dec(t[2], p + '.2', fresh)}; "
                f"pure ({k}, {w})) | _ => none)")
    if tag == "tuple":
        ds = [fresh("d") for _ in t[1]]
        vs = [fresh("t") for _ in t[1]]
        binds = "; ".join(f"let {v} ← {dec(x, di, fresh)}" for x, di, v in zip(t[1], ds, vs))
        return (f"(match {d} with | Data.List [{', '.join(ds)}] => (do {binds}; "
                f"pure ({', '.join(vs)})) | _ => none)")
    raise AssertionError(t)


def emit_decl(name, kind, ctors):
    fresh = Fresh()
    out = []
    if kind == "structure":
        (ctor, index, fields), = ctors
        out.append(f"structure {name} where")
        for f, t in fields:
            out.append(f"  {f} : {lean_type(t)}")
        if not fields:
            out[-1] += " mk ::"
        out.append("")
        out.append(f"instance : IsData {name} where")
        items = ", ".join(enc(t, f"x.{f}", fresh) for f, t in fields)
        out.append(f"  toData {'x' if fields else '_'} := Data.Constr {index} [{items}]")
        ds = [f"d{j}" for j in range(len(fields))]
        out.append("  fromData")
        if fields:
            out.append(f"    | Data.Constr {index} [{', '.join(ds)}] => do")
            for (f, t), dj, j in zip(fields, ds, range(len(fields))):
                out.append(f"        let a{j} ← {dec(t, dj, fresh)}")
            out.append(f"        pure ({name}.mk {' '.join(f'a{j}' for j in range(len(fields)))})")
        else:
            out.append(f"    | Data.Constr {index} [] => some {name}.mk")
        out.append("    | _ => none")
    else:
        out.append(f"inductive {name} where")
        for ctor, index, fields in ctors:
            args = " ".join(f"({f} : {lean_type(t)})" for f, t in fields)
            out.append(f"  | {ctor}{(' ' + args) if args else ''}")
        out.append("")
        out.append(f"instance : IsData {name} where")
        out.append("  toData")
        for ctor, index, fields in ctors:
            vs = [f"a{j}" for j in range(len(fields))]
            pat = f"{name}.{ctor}" + "".join(" " + v for v in vs)
            items = ", ".join(enc(t, v, fresh) for (f, t), v in zip(fields, vs))
            out.append(f"    | {pat} => Data.Constr {index} [{items}]")
        out.append("  fromData")
        for ctor, index, fields in ctors:
            ds = [f"d{j}" for j in range(len(fields))]
            if fields:
                out.append(f"    | Data.Constr {index} [{', '.join(ds)}] => do")
                for (f, t), dj, j in zip(fields, ds, range(len(fields))):
                    out.append(f"        let a{j} ← {dec(t, dj, fresh)}")
                out.append(f"        pure ({name}.{ctor} {' '.join(f'a{j}' for j in range(len(fields)))})")
            else:
                out.append(f"    | Data.Constr {index} [] => some {name}.{ctor}")
        out.append("    | _ => none")
    return out


# ---- validators ----

def find_entries(bp, name):
    """Blueprint titles are `module.validator.handler`; `name` is `module.validator` or `validator`."""
    def head(v):
        return ".".join(v["title"].split(".")[:2])
    entries = bp.get("validators", [])
    heads = sorted({head(v) for v in entries
                    if head(v) == name or ("." not in name and head(v).split(".")[1] == name)})
    if not heads:
        raise ExtractError(f"no validator `{name}` in the blueprint")
    if len(heads) > 1:
        raise ExtractError(f"`{name}` is ambiguous: {', '.join(heads)}")
    return [v for v in entries if head(v) == heads[0]]


PURPOSES = ["spend", "mint", "withdraw", "publish", "vote", "propose"]


@dataclass
class Handler:
    purpose: str
    redeemer_kind: str          # constructors | integer | bytes | list | map | any
    redeemer_ctors: list        # [(Lean constructor, index, [(field, type)])] when a named type, else []
    redeemer_type: object       # the type description, or None without a redeemer schema


@dataclass
class ValidatorInfo:
    head: str                   # `module.validator`
    module_name: str            # Lean file name, e.g. `LinearVesting`
    namespace: str              # e.g. `Formal.Blueprint.LinearVesting`
    handlers: list              # [Handler], without the `else` fallback
    has_params: bool
    datum_kind: str             # kind of the spend datum, or "none" without a spend handler
    datum_ctors: list           # constructors of the spend datum when a named type, else []
    datum_type: object          # the spend datum's type description, or None
    translator: object          # for the fields of named types
    warnings: list


def redeemer_kind(t):
    """The top-level form of a datum or redeemer type, which decides its malformed forms."""
    return {"int": "integer", "bytes": "bytes", "list": "list", "tuple": "list",
            "map": "map", "data": "any"}.get(t[0], "constructors")


def extract(bp, name, scripts_dir):
    """Pass 1: (Lean lines without the closing `end`, cbor path, compiled code, ValidatorInfo)."""
    return generate(bp, name, scripts_dir)


def render(lines, info, with_checks):
    """The validator's Lean file: pass 1's declarations, then pass 2's checks."""
    out = list(lines)
    if with_checks:
        i = out.index("import CardanoLedgerApi")
        out[i + 1:i + 1] = ["import Blaster", "import Formal.Universal.Properties", "",
                            "-- Check one proof at a time, in order: Lean prints each result as it",
                            "-- comes, and a slow check cannot hold up the ones before it.",
                            "set_option Elab.async false"]
        out += checks(info)
    out.append(f"end {info.namespace}")
    return "\n".join(out) + "\n"


def generate(bp, name, scripts_dir):
    entries = find_entries(bp, name)
    head = ".".join(entries[0]["title"].split(".")[:2])
    module, validator = head.split(".")
    codes = {e.get("compiledCode") for e in entries}
    if len(codes) != 1:
        raise ExtractError(f"handlers of `{head}` have different compiled code")
    params = entries[0].get("parameters", [])
    tr = Translator(bp.get("definitions", {}))

    handlers = []
    for e in entries:
        purpose = e["title"].split(".")[-1]
        datum = tr.ty(e["datum"]["schema"], f"{purpose} datum") if e.get("datum") else None
        redeemer = tr.ty(e["redeemer"]["schema"], f"{purpose} redeemer") if e.get("redeemer") else None
        handlers.append((purpose, datum, redeemer))
    ptys = [(ident(p.get("title"), f"param{j}"), tr.ty(p["schema"], f"parameter {p.get('title', j)}"))
            for j, p in enumerate(params)]

    ns = "Formal.Blueprint." + camel(validator)
    cbor_path = f"{scripts_dir}/{module.replace('/', '.')}.{validator}.cbor"
    compiler = bp.get("preamble", {}).get("compiler", {})
    version = bp.get("preamble", {}).get("plutusVersion", "v3")
    if version != "v3":
        raise ExtractError(f"plutusVersion {version} is not supported")

    L = []
    L.append(f"-- Generated by process_blueprint.py from the blueprint entry `{head}`"
             f" ({compiler.get('name', '?')} {compiler.get('version', '?')}). Do not edit; regenerate.")
    L += ["import PlutusCore.UPLC", "import CardanoLedgerApi", ""]
    L.append(f"namespace {ns}")
    L.append("")
    L += ["open PlutusCore.Data (Data)",
          "open PlutusCore.ByteString (ByteString)",
          "open PlutusCore.UPLC.Term (Term Const Program)",
          "open PlutusCore.UPLC.CekMachine (cekExecuteProgram State)",
          "open CardanoLedgerApi.IsData.Class (IsData toTerm)",
          "open CardanoLedgerApi.V3 (Address Credential StakingCredential ScriptContext TxOutRef)",
          ""]
    for w in tr.warnings:
        L.append(f"-- WARNING: {w}")
    if tr.warnings:
        L.append("")

    L.append("/-! ## Types -/")
    L.append("")
    for key in tr.order:
        kind, ctors = tr.decls[key]
        L.append(f"/-- `{key}` -/")
        L += emit_decl(tr.named[key], kind, ctors)
        L.append("")

    L.append("/-! ## Handlers -/")
    L.append("")
    declared = [p for p, _, _ in handlers if p != "else"]
    L.append(f"/-- Purposes with a handler in the blueprint (the `else` fallback is not listed). -/")
    L.append("def handlers : List String := [" + ", ".join(f'"{p}"' for p in declared) + "]")
    L.append("")
    for purpose, datum, redeemer in handlers:
        if purpose == "else":
            continue
        P = camel(purpose)
        if datum is not None:
            L.append(f"abbrev {P}Datum := {lean_type(datum)}")
        if redeemer is not None:
            L.append(f"abbrev {P}Redeemer := {lean_type(redeemer)}")
    L.append("")

    L.append("/-! ## Parameters and script -/")
    L.append("")
    fresh = Fresh()
    if ptys:
        L.append("/-- Parameters, in the order the script takes them. -/")
        L.append("structure Params where")
        for f, t in ptys:
            L.append(f"  {f} : {lean_type(t)}")
        L.append("")
        L.append("/-- The script's arguments: the parameters, then the script context. -/")
        L.append("def args (p : Params) (ctx : ScriptContext) : List Term :=")
        items = [f"Term.Const (Const.Data ({enc(t, 'p.' + f, fresh)}))" for f, t in ptys] + ["toTerm ctx"]
        L.append("  [" + ",\n   ".join(items) + "]")
        sig, call = "(p : Params) (ctx : ScriptContext)", "(args p ctx)"
    else:
        L.append("/-- The script's arguments: the script context only (no parameters). -/")
        L.append("def args (ctx : ScriptContext) : List Term := [toTerm ctx]")
        sig, call = "(ctx : ScriptContext)", "(args ctx)"
    L.append("")
    # `#import_uplc` may declare at the root namespace, so the name carries the validator's.
    script = camel(validator)[:1].lower() + camel(validator)[1:] + "Script"
    L.append(f'#import_uplc {script} PlutusV3 single_cbor_hex "{cbor_path}"')
    L.append("")
    L.append(f"def program : Program := {script}.script")
    L.append("")
    L.append(f'/-- The script hash recorded in the blueprint (hex). -/')
    L.append(f'def scriptHashHex : String := "{entries[0].get("hash", "")}"')
    L.append("")
    L.append("/-- The script accepts within `fuel` steps. -/")
    L.append(f"def accepts (fuel : Nat) {sig} : Prop :=")
    L.append(f"  cekExecuteProgram program {call} fuel = .Halt (.VCon Const.Unit)")
    L.append("")
    def ctors_of(t):
        if t is None or t[0] != "named":
            return []
        key = next(k for k, n in tr.named.items() if n == t[1])
        kind, ctors = tr.decls[key]
        # The Lean constructor: `T.mk` for a structure, `T.Ctor` for an inductive.
        return [(f"{t[1]}.{'mk' if kind == 'structure' else c}", i, fs) for c, i, fs in ctors]

    datum_kind, datum_ctors, datum_type = "none", [], None
    infos = []
    for purpose, datum, redeemer in handlers:
        if purpose == "else":
            continue
        if purpose not in PURPOSES:
            raise ExtractError(f"unknown handler purpose `{purpose}`")
        kind = redeemer_kind(redeemer) if redeemer is not None else "any"
        infos.append(Handler(purpose, kind, ctors_of(redeemer), redeemer))
        if purpose == "spend":
            datum_kind = redeemer_kind(datum) if datum is not None else "any"
            datum_ctors, datum_type = ctors_of(datum), datum
    info = ValidatorInfo(head, camel(validator), ns, infos, bool(ptys), datum_kind, datum_ctors,
                         datum_type, tr, tr.warnings)
    return L, cbor_path, entries[0]["compiledCode"], info


# ---- pass 2: the universal checks ----

# Builders over every transaction, in Formal/Universal/Properties.lean.
EVERY = {"spend": "EverySpend", "mint": "EveryMint", "withdraw": "EveryWithdraw",
         "publish": "EveryPublish", "vote": "EveryVote", "propose": "EveryPropose"}
NOUN = {"spend": "spend", "mint": "mint", "withdraw": "withdrawal", "publish": "certificate",
        "vote": "vote", "propose": "proposal"}

# The forms of Data that are malformed for each kind of datum or redeemer:
# (name, text, variable, its type, the Data term).
FORMS = {"int": ("an integer", "n", "Int", "Data.I n"),
         "bytes": ("a byte string", "b", "ByteString", "Data.B b"),
         "list": ("a list", "l", "List Data", "Data.List l"),
         "map": ("a map", "m", "List (Data × Data)", "Data.Map m")}
MALFORMED = {"constructors": ["int", "bytes", "list", "map"], "integer": ["bytes", "list", "map"],
             "bytes": ["int", "list", "map"], "list": ["int", "bytes", "map"],
             "map": ["int", "bytes", "list"], "any": []}


class Terms:
    """Data terms for well-formed values of a type, with their variables. Every leaf (integer,
    byte string, credential, ...) is a variable; every list and map is empty, so that the script
    never walks a list of unknown length; an `Option` or a sum that holds a list somewhere is its
    first alternative, for the same reason. A type with no list anywhere is one typed variable."""

    def __init__(self, tr):
        self.tr = tr
        self.by_name = {n: k for k, n in tr.named.items()}
        self.n = 0
        self.binders = []

    def var(self, ty):
        self.n += 1
        v = f"x{self.n}"
        self.binders.append(f"({v} : {ty})")
        return v

    def has_list(self, t, seen=()):
        tag = t[0]
        if tag in ("list", "map"):
            return True
        if tag == "option":
            return self.has_list(t[1], seen)
        if tag == "tuple":
            return any(self.has_list(x, seen) for x in t[1])
        if tag == "named":
            key = self.by_name[t[1]]
            if key in seen:
                return True
            _, ctors = self.tr.decls[key]
            return any(self.has_list(ft, seen + (key,)) for _, _, fs in ctors for _, ft in fs)
        return False

    def term(self, t):
        tag = t[0]
        if tag in ("list", "map"):
            return "(Data.List [])" if tag == "list" else "(Data.Map [])"
        if not self.has_list(t):
            return f"({enc(t, self.var(lean_type(t)), Fresh())})"
        if tag == "option":
            return "(Data.Constr 1 [])"
        if tag == "tuple":
            return "(Data.List [" + ", ".join(self.term(x) for x in t[1]) + "])"
        _, ctors = self.tr.decls[self.by_name[t[1]]]
        _, index, fields = ctors[0]
        return self.ctor(index, fields)

    def ctor(self, index, fields, replace=None):
        """`Data.Constr index [fields]`, with field j replaced by `replace[j]` when given."""
        items = [(replace or {}).get(j) or self.term(ft) for j, (_, ft) in enumerate(fields)]
        return f"(Data.Constr {index} [{', '.join(items)}])"

    def wrong(self, t):
        """A Data term of the wrong form for a field of type t, or None for a Data field."""
        if t[0] == "data":
            return None
        if t[0] == "int":
            return f"(Data.B {self.var('ByteString')})"
        return f"(Data.I {self.var('Int')})"


WIDTH = 100


def chunks(text, brackets="([{⟨"):
    """`text` split at the spaces that are outside the given kinds of bracket."""
    closing = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
    opens, closes = set(brackets), {closing[b] for b in brackets}
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in opens:
            depth += 1
        elif ch in closes:
            depth -= 1
        if ch == " " and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [c for c in out if c]


def fill(text, indent, width=WIDTH):
    """`text` in lines of at most `width` characters where possible, broken at spaces outside
    brackets first and inside parentheses or square brackets only when a bracketed part is too
    long. A structure update `{ ... }` is never broken: Lean requires a field's value to stay to
    the right of the field. The first line is indented by `indent` spaces, the others by 2 more."""
    lines, line = [], " " * indent
    for c in chunks(text):
        parts = [c] if indent + 2 + len(c) <= width else chunks(c, "{")
        for w in parts:
            if line.strip() and len(line) + 1 + len(w) > width:
                lines.append(line)
                line = " " * (indent + 2) + w
            else:
                line = line + (" " if line.strip() else "") + w
    lines.append(line)
    return lines


def comment(text):
    """`text` as `--` comment lines of at most WIDTH characters."""
    return ["-- " + l.strip() for l in fill(text, 0, WIDTH - 3)]


def theorem_lines(name, quant, claim, proof):
    """A theorem with its quantified variables on one line and its claim on the next, both
    indented under the name, each wrapped at WIDTH characters."""
    out = [f"theorem {name} :"]
    if quant:
        out += fill(quant, 4)
    keep = (":= " + proof).replace(" ", chr(0))
    out += [l.replace(chr(0), " ") for l in fill(f"{claim} {keep}", 6 if quant else 4)]
    return out


def short(ctor):
    """`Sale.SaleRedeemer.Buy` -> `Buy`; `T.mk` -> `T`'s last segment."""
    return (ctor.split(".")[-2] if ctor.endswith(".mk") else ctor.split(".")[-1]).strip("«»")


def plain(field):
    return field.strip("«»")


def checks(info):
    """Pass 2: the Lean lines of the G checks (proved by Blaster) and the H checks (on honest
    transactions; `sorry` until those are written)."""
    declared = [h.purpose for h in info.handlers]
    undeclared = [p for p in PURPOSES if p not in declared]
    P = info.has_params
    binder = " (p : Params)" if P else ""
    pa = " p" if P else ""
    tr = info.translator
    spend = next((h for h in info.handlers if h.purpose == "spend"), None)
    typed_datum = spend is not None and info.datum_kind not in ("any", "none")
    G, H = [], []

    def g(prop, text, name, binders, ctx):
        quant = f"∀ {' '.join(binders)}," if binders else ""
        G.extend(comment(f"{prop}: {text}"))
        G.extend(theorem_lines(f"{name}{binder}", quant, f"¬ accepts ledgerFuel{pa} ({ctx})", "by blaster"))
        G.append("")

    def actions(h):
        """[(name, binders, Data term)]: per redeemer constructor, with well-formed fields; one
        entry `any` for a redeemer that is not a constructor type."""
        if h.redeemer_type is None or h.redeemer_kind == "any":
            return [("any", ["(r : Data)"], "r")]
        if not h.redeemer_ctors:
            w = Terms(tr)
            return [("any", w.binders, w.term(h.redeemer_type))]
        out = []
        for ctor, index, fields in h.redeemer_ctors:
            w = Terms(tr)
            out.append((short(ctor), w.binders, w.ctor(index, fields)))
        return out

    def malformed(kind, ctors, first_var):
        """[(suffix, text, binders, Data term)]: the ways a value of a type of this kind and these
        constructors fails to decode, each with its variables."""
        out = []
        for form in MALFORMED[kind]:
            text, v, ty, term = FORMS[form]
            out.append((f"wrongForm_{form}", f"{text} instead of the declared type", [f"({v} : {ty})"], f"({term})"))
        if kind == "constructors" and ctors:
            k = len(ctors)
            for idx in (k, k + 1):
                out.append((f"unknownIndex{idx}", f"a constructor with the unknown index {idx}",
                            ["(fs : List Data)"], f"(Data.Constr {idx} fs)"))
            for ctor, index, fields in ctors:
                c = short(ctor)
                w = Terms(tr)
                w.n = first_var
                items = [w.term(ft) for _, ft in fields]
                extra = w.var("Data")
                out.append((f"{c}_extraField", f"{c} with an extra field", w.binders,
                            f"(Data.Constr {index} [{', '.join(items + [extra])}])"))
                if fields:
                    w = Terms(tr)
                    w.n = first_var
                    items = [w.term(ft) for _, ft in fields[:-1]]
                    out.append((f"{c}_missingField", f"{c} without its last field", w.binders,
                                f"(Data.Constr {index} [{', '.join(items)}])"))
                for j, (f, ft) in enumerate(fields):
                    w = Terms(tr)
                    w.n = first_var
                    bad = w.wrong(ft)
                    if bad is not None:
                        out.append((f"{c}_wrongKind_{plain(f)}", f"{c} with field `{plain(f)}` of the wrong kind",
                                    w.binders, w.ctor(index, fields, {j: bad})))
        return out

    # ---- G1: a purpose with no handler is rejected.
    for q in undeclared:
        S = EVERY[q]
        g("G1 (UP-001)", f"no {NOUN[q]} is accepted, since there is no {q} handler.",
          f"g1_{q}", ["(r : Data)", f"(t : {S})"], f"{S}.ctx t r")

    # ---- G2: a redeemer that does not decode as its declared type is rejected.
    for h in info.handlers:
        S = EVERY[h.purpose]
        for sfx, text, bs, term in malformed(h.redeemer_kind, h.redeemer_ctors, 0):
            g("G2 (UP-005)", f"no {NOUN[h.purpose]} is accepted whose redeemer is {text}.",
              f"g2_{h.purpose}_{sfx}", bs + [f"(t : {S})"], f"{S}.ctx t {term}")

    # ---- H: honest transactions, each changed in one way.
    hp = " honestParams" if P else ""
    if P:
        H += ["/-- The parameters the honest transactions are for. -/", "def honestParams : Params := sorry", ""]
    malformed_output_datum = {"constructors": "Data.I 0", "integer": "Data.B \"\"", "bytes": "Data.I 0",
                              "list": "Data.I 0", "map": "Data.I 0"}.get(info.datum_kind)

    def hthm(prop, name, statement, text):
        cs = chunks(statement)
        k = next(i for i, c in enumerate(cs) if c in ("rejects", "accepts"))
        H.extend(comment(f"{prop}: {text}"))
        H.extend(theorem_lines(name, " ".join(cs[:k]), " ".join(cs[k:]), "by sorry"))
        H.append("")

    for h in info.handlers:
        if h.purpose not in ("spend", "mint", "withdraw"):
            continue
        for a, _, _ in actions(h):
            x = f"honest_{h.purpose}_{a}"
            prot = f"{x}_protected"
            outs = f"(outputsOf {x})"
            sigs = f"(signatoriesOf {x})"
            acc = f"accepts ledgerFuel{hp}"
            rej = f"rejects ledgerFuel{hp}"
            on = "" if a == "any" else f" with redeemer {a}"
            H += [f"/-- A {NOUN[h.purpose]}{on} that the script accepts. -/",
                  f"def {x} : ScriptContext := sorry",
                  f"/-- The positions of the outputs of `{x}` that the script must protect. -/",
                  f"def {prot} : List Nat := sorry", ""]
            n = f"{h.purpose}_{a}"
            hthm("H1 (UP-000)", f"h1_{n}", f"{acc} {x}",
                 "the honest transaction is accepted (this is what makes the other H checks meaningful).")
            hthm("H2 (UP-002)", f"h2_{n}", f"{rej} (withSignatories {x} [])", "without any signatory, it is rejected.")
            hthm("H3 (UP-012)", f"h3_{n}", f"∀ i : Nat, i < {sigs}.length → {rej} (withSignatories {x} ({sigs}.eraseIdx i))",
                 "without any one of its signatories, it is rejected.")
            hthm("H4", f"h4_{n}", f"∀ (i : Nat) (k : PubKeyHash), i < {sigs}.length → k ∉ {sigs} → "
                 f"{rej} (withSignatories {x} ({sigs}.set i k))", "with a signatory replaced by another key, it is rejected.")
            hthm("H5 (UP-011)", f"h5_{n}", f"∀ i ∈ {prot}, ∀ addr : Address, (∀ o, {outs}[i]? = some o → addr ≠ o.txOutAddress) → "
                 f"{rej} (changeOutput {x} i (fun o => {{ o with txOutAddress := addr }}))",
                 "with a protected output sent to another address, it is rejected.")
            hthm("H6", f"h6_{n}", f"∀ i ∈ {prot}, {rej} (changeOutput {x} i (fun o => {{ o with txOutValue := lowerLovelace o.txOutValue }}))",
                 "with 1 lovelace less in a protected output, it is rejected.")
            hthm("H7 (UP-014)", f"h7_{n}", f"∀ i ∈ {prot}, ∀ d : OutputDatum, (∀ o, {outs}[i]? = some o → d ≠ o.txOutDatum) → "
                 f"{rej} (changeOutput {x} i (fun o => {{ o with txOutDatum := d }}))",
                 "with a protected output given another datum, it is rejected.")
            if h.purpose == "spend":
                if malformed_output_datum:
                    hthm("H8 (UP-006)", f"h8_{n}", f"∀ i ∈ continuingPositions {x}, {rej} (changeOutput {x} i "
                         f"(fun o => {{ o with txOutDatum := .OutputDatum ({malformed_output_datum}) }}))",
                         "with an output back to the script given a malformed datum, it is rejected.")
                hthm("H9 (UP-007)", f"h9_{n}", f"∀ i ∈ continuingPositions {x}, ∀ sc : Option StakingCredential, "
                     f"(∀ o, {outs}[i]? = some o → sc ≠ o.txOutAddress.addressStakingCredential) → {rej} (changeOutput {x} i "
                     f"(fun o => {{ o with txOutAddress := {{ o.txOutAddress with addressStakingCredential := sc }} }}))",
                     "with an output back to the script given another staking credential, it is rejected.")
                hthm("H10 (UP-008)", f"h10_{n}", f"∀ i ∈ continuingPositions {x}, {rej} (changeOutput {x} i "
                     f"(fun o => {{ o with txOutValue := withJunkToken o.txOutValue }}))",
                     "with a junk token added to an output back to the script, it is rejected.")
                hthm("H11 (UP-010)", f"h11_{n}", f"∀ ref : TxOutRef, (∀ i ∈ inputsOf {x}, "
                     f"i.txInInfoOutRef ≠ ref) → {rej} (duplicateOwnInput {x} ref)",
                     "with a second input from the script that the same outputs must pay for, it is rejected.")
            hthm("H12 (UP-013)", f"h12_{n}", f"{rej} (withRange {x} rangeAlways)",
                 "with an unbounded validity range, it is rejected (only for actions that depend on time).")
            if h.purpose == "mint":
                hthm("H13 (UP-016)", f"h13_{n}", f"{rej} (mintOneMore {x})",
                     "with one more token minted under the script's own policy, it is rejected.")
                hthm("H14", f"h14_{n}", f"{rej} (withMint {x} (negateMint (mintOf {x})))",
                     "with the mint turned into a burn, or the other way round, it is rejected.")
            for other, oindex, ofields in (h.redeemer_ctors or []):
                if short(other) == a:
                    continue
                w = Terms(tr)
                term = w.ctor(oindex, ofields)
                quant = f"∀ {' '.join(w.binders)}, " if w.binders else ""
                hthm("H15", f"h15_{n}_as{short(other)}", f"{quant}{rej} (withRedeemer {x} {term})",
                     f"with the redeemer changed to {short(other)}, it is rejected.")
            hthm("H16 (UP-015)", f"h16_{n}", f"{acc} (withOutputs {x} {outs}.reverse)",
                 "with its outputs in reverse order, it is still accepted.")
            hthm("H17", f"h17_{n}", f"{acc} (withOutputs {x} (List.append {outs} [unrelatedOutput]))",
                 "with an unrelated output added, it is still accepted (review: some validators require exact counts).")
            if h.purpose == "spend" and typed_datum:
                for dsfx, text, bs, term in malformed(info.datum_kind, info.datum_ctors, 100):
                    quant = f"∀ {' '.join(bs)}, " if bs else ""
                    hthm("H18", f"h18_{n}_{dsfx}", f"{quant}{rej} (withSpendDatum {x} {term})",
                         f"with its datum replaced by {text}, it is rejected.")
            if h.purpose == "spend":
                hthm("H19", f"h19_{n}", f"{rej} (withoutSpendDatum {x})",
                     "without a datum, it is rejected (review: some validators allow this on purpose).")
    H += ["-- H20 (UP-009), a spent input with a hashed datum, is not written: the ledger model treats a",
          "-- resolved datum on a hashed-datum input as invalid.", ""]

    ng = len([l for l in G if l.startswith("theorem ")])
    nh = len([l for l in H if l.startswith("theorem ")])
    L = ["/-! ## Universal checks",
         "",
         f"Declared: [{', '.join(declared)}]; " + ("parameters open." if P else "no parameters."),
         "",
         f"G checks ({ng}), proved by Blaster over every transaction (everything not named in the",
         "statement is a variable). Where a malformed value needs well-formed fields next to the",
         "malformed one, their leaves are variables and their lists and maps are empty.",
         "  G1 (UP-001)  a purpose with no handler is rejected.",
         "  G2 (UP-005)  a redeemer that does not decode as its declared type is rejected.",
         "The datum checks are H18 and H19. Stated over every transaction, most of them did not finish",
         "within 2 minutes on linear_vesting or sale: the compiled script reads its datum only where it",
         "uses a field, often after reading the transaction.",
         "",
         f"H checks ({nh}), on honest transactions: `sorry` until the honest transactions below are",
         "written (each `def honest_...`), then `by blaster`. Each changes one thing in an accepted",
         "transaction and states the verdict it must then have.",
         "-/", "", "section UniversalChecks", "", "open Formal.Universal.Properties",
         "open CardanoLedgerApi.V3 (PubKeyHash OutputDatum)", "",
         "/-- The script genuinely fails within `fuel` steps (running out of steps is not a failure). -/",
         f"def rejects (fuel : Nat){binder} (ctx : ScriptContext) : Prop :=",
         f"  rejectedWithin program (args{pa} ctx) fuel", "",
         "/-! ### G checks -/", ""] + G + ["/-! ### H checks -/", ""] + H
    L += ["end UniversalChecks", ""]
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blueprint", nargs="?")
    ap.add_argument("validator", nargs="?", help="`module.validator` or `validator`")
    ap.add_argument("--out", default="Formal/Blueprint", help="directory for the generated Lean file")
    ap.add_argument("--scripts", default="Scripts", help="directory for the .cbor file, as seen by Lean")
    ap.add_argument("--no-checks", action="store_true", help="run pass 1 only (no theorems, no Blaster)")
    ap.add_argument("--translation", action="store_true", help="print the translation table and exit")
    a = ap.parse_args()
    if a.translation:
        print(TRANSLATION)
        return
    if not (a.blueprint and a.validator):
        ap.error("a blueprint and a validator are required")
    try:
        bp = json.loads(Path(a.blueprint).read_text())
        lines, cbor_path, code, info = extract(bp, a.validator, a.scripts)
        lean = render(lines, info, not a.no_checks)
    except (ExtractError, KeyError, json.JSONDecodeError) as e:
        sys.exit(f"process_blueprint: {e}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{info.module_name}.lean").write_text(lean)
    Path(cbor_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cbor_path).write_text(code)
    print(f"wrote {out / (info.module_name + '.lean')} and {cbor_path}")
    for w in info.warnings:
        print(f"warning: {w}")


if __name__ == "__main__":
    main()
