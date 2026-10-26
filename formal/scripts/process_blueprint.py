#!/usr/bin/env python3
"""Turn one validator of an Aiken blueprint (plutus.json) into Lean, in two passes.

Usage, from formal/ (scripts/universal.py calls it for the justfile's validator recipes):
  scripts/process_blueprint.py ../onchain/plutus.json linear_vesting --out Formal/Vesting/Linear/Blueprint
  scripts/process_blueprint.py ../onchain/plutus.json dao/stake.stake --out Formal/Dao/Stake/Blueprint
  scripts/process_blueprint.py ../onchain/plutus.json linear_vesting --cbor-only --scripts Scripts

Writes into the folder given by --out, which is under Formal/ (the Lean module names follow it):
  Types.lean    pass 1: types, IsData instances, parameters, arguments, the script, `accepts`,
                `rejects`. Replaced on every run.
  Checks.lean   pass 2: the universal checks, in the order of docs/Universal/PROPERTIES.md: the
                family named with --check, and someAccepted. Replaced on every run.
  Tx.lean       the honest transactions, written by the validator's author. Written as a skeleton
                with `sorry` only when it does not exist; never replaced.
`--no-checks` writes Types.lean only.
`--cbor-only` writes only <scripts>/<module>.<name>.cbor (the blueprint's compiledCode) and prints
its path; Types.lean reads it with `#import_uplc`.

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


def cbor_path_of(entries, scripts_dir):
    """`<scripts>/<module>.<validator>.cbor`, with `/` in the module replaced by `.`."""
    module, validator = entries[0]["title"].split(".")[:2]
    return f"{scripts_dir}/{module.replace('/', '.')}.{validator}.cbor"


def compiled_code(entries):
    """The compiledCode shared by all handlers of one validator."""
    head = ".".join(entries[0]["title"].split(".")[:2])
    codes = {e.get("compiledCode") for e in entries}
    if len(codes) != 1:
        raise ExtractError(f"handlers of `{head}` have different compiled code")
    return entries[0]["compiledCode"]


def module_prefix(folder):
    """`Formal/Vesting/Linear/Blueprint` -> `Formal.Vesting.Linear.Blueprint`."""
    parts = [p for p in Path(folder).parts if p not in ("", ".")]
    if not parts or parts[0] != "Formal":
        raise ExtractError(f"the folder `{folder}` is not under Formal/; Lean module names follow the path")
    for p in parts:
        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", p):
            raise ExtractError(f"the folder name `{p}` in `{folder}` is not a Lean module name")
    return ".".join(parts)


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
    prefix: str                 # module prefix and namespace, e.g. `Formal.Vesting.Linear.Blueprint`
    origin: str                 # the blueprint entry and compiler, for the files' first line
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


def generate(bp, name, prefix, scripts_dir):
    """Pass 1: (the lines of Types.lean without the closing `end`, ValidatorInfo)."""
    entries = find_entries(bp, name)
    head = ".".join(entries[0]["title"].split(".")[:2])
    module, validator = head.split(".")
    compiled_code(entries)
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

    cbor_path = cbor_path_of(entries, scripts_dir)
    compiler = bp.get("preamble", {}).get("compiler", {})
    version = bp.get("preamble", {}).get("plutusVersion", "v3")
    if version != "v3":
        raise ExtractError(f"plutusVersion {version} is not supported")
    origin = f"the blueprint entry `{head}` ({compiler.get('name', '?')} {compiler.get('version', '?')})"

    L = []
    L.append(f"-- Generated by process_blueprint.py from {origin}. Do not edit; regenerate.")
    L += ["import PlutusCore.UPLC", "import CardanoLedgerApi", "import Formal.Universal.Properties", ""]
    L.append(f"namespace {prefix}")
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
    L.append("/-- The script genuinely fails within `fuel` steps (running out of steps is not a failure). -/")
    L.append(f"def rejects (fuel : Nat) {sig} : Prop :=")
    L.append(f"  Formal.Universal.Properties.rejectedWithin program {call} fuel")
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
    info = ValidatorInfo(head, prefix, origin, infos, bool(ptys), datum_kind, datum_ctors,
                         datum_type, tr, tr.warnings)
    return L, info


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


def split_top(text, sep):
    """`text` split at the occurrences of `sep` outside brackets."""
    pairs = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
    out, depth, cur, i = [], 0, "", 0
    while i < len(text):
        ch = text[i]
        if depth == 0 and text.startswith(sep, i):
            out.append(cur)
            cur, i = "", i + len(sep)
            continue
        if ch in pairs:
            depth += 1
        elif ch in pairs.values():
            depth -= 1
        cur += ch
        i += 1
    out.append(cur)
    return out


def theorem_lines(name, quant, claim, proof):
    """A theorem with its quantified variables on one line and its claim below, both indented
    under the name. A claim made of hypotheses (`→`) or conjuncts (`∧`) has one per line, each
    wrapped at WIDTH characters."""
    out = [f"theorem {name} :"]
    if quant:
        out += fill(quant, 4)
    ind = 6 if quant else 4
    for sep in (" → ", " ∧ "):
        parts = split_top(claim, sep)
        if len(parts) > 1:
            break
    for k, part in enumerate(parts):
        last = k == len(parts) - 1
        end = f" := {proof}" if last else sep.rstrip()
        alts = split_top(part[1:-1], " ∨ ") if part.startswith("(") and part.endswith(")") else [part]
        if len(alts) > 1:
            pieces = [("(" if j == 0 else "") + alt + (" ∨" if j < len(alts) - 1 else ")" + end)
                      for j, alt in enumerate(alts)]
        else:
            pieces = [part + end]
        for j, piece in enumerate(pieces):
            keep = piece.replace(":= " + proof, (":= " + proof).replace(" ", chr(0)))
            out += [l.replace(chr(0), " ") for l in fill(keep, ind + (1 if j else 0))]
    return out


def short(ctor):
    """`Sale.SaleRedeemer.Buy` -> `Buy`; `T.mk` -> `T`'s last segment."""
    return (ctor.split(".")[-2] if ctor.endswith(".mk") else ctor.split(".")[-1]).strip("«»")


def plain(field):
    return field.strip("«»")


def actions(h, tr):
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


def honest_handlers(info):
    """The handlers that get shapes, and the checks over shapes."""
    return [h for h in info.handlers if h.purpose in ("spend", "mint", "withdraw")]


def malformed(tr, kind, ctors, first_var, fixed=False):
    """[(suffix, text, binders, Data term)]: the ways a value of a type of this kind and these
    constructors fails to decode, each with its variables. With `fixed`, a constructor with an
    unknown index has the first constructor's fields instead of a list of variable length."""
    out = []
    for form in MALFORMED[kind]:
        text, v, ty, term = FORMS[form]
        out.append((f"wrongForm_{form}", f"{text} instead of the declared type", [f"({v} : {ty})"], f"({term})"))
    if kind == "constructors" and ctors:
        k = len(ctors)
        for idx in (k, k + 1):
            if fixed:
                w = Terms(tr)
                w.n = first_var
                term = w.ctor(idx, ctors[0][2])
                out.append((f"unknownIndex{idx}", f"a constructor with the unknown index {idx}", w.binders, term))
            else:
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


# The sections of the universal checks, in order, and their families, each in its section:
# the checks that must reject first, then the ones that must still accept. Checks are named by
# family; docs/Universal/PROPERTIES.md numbers them.
SECTIONS = [
    ("sanity", "Sanity", ["someAccepted", "someRejected"]),
    ("arguments", "Purpose and arguments",
     ["otherPurpose", "malformedRedeemer", "otherRedeemer", "spendDatumTag", "noSpendDatum"]),
    ("signatories", "Signatories", ["dropSigner", "wrongSigner", "extraSigner"]),
    ("inputs", "Inputs", ["unrelatedInput"]),
    ("outputs", "Outputs", ["reverseOutputs", "rotateOutputs", "unrelatedOutput"]),
    ("continuations", "Outputs back to the script",
     ["continuationElsewhere", "continuationStake", "continuationOtherDatum", "continuationDatumTag",
      "junkToken", "continuationRefScript"]),
    ("mint", "Mint", ["extraMint", "mintAsBurn", "unrelatedMint"]),
    ("range", "Validity range", ["unboundedRange"]),
    ("multipleInputs", "Several script inputs", ["doubleSatisfaction"]),
]
FAMILIES = [f for _, _, fs in SECTIONS for f in fs]
SECTION_OF = {f: s for s, _, fs in SECTIONS for f in fs}
# Always generated: the other checks say nothing unless some honest transaction is accepted.
ALWAYS = "someAccepted"


def lower_first(s):
    return s[:1].lower() + s[1:]


def shape_names(info):
    """{(purpose, action): the shape's name in Tx.lean}: the action, lower-cased first, or the
    purpose for a redeemer that is not a constructor type; with the purpose in front when two
    handlers share an action."""
    pairs = [(h.purpose, a) for h in honest_handlers(info) for a, _, _ in actions(h, info.translator)]
    base = {pa: (pa[0] if pa[1] == "any" else lower_first(pa[1])) for pa in pairs}
    out = {}
    for pa, n in base.items():
        if list(base.values()).count(n) > 1:
            n = pa[0] + pa[1][:1].upper() + pa[1][1:]
        out[pa] = f"«{n}»" if n in LEAN_RESERVED else n
    return out


def docstring(text, indent=0):
    """`text` as a `/-- ... -/` doc comment of at most WIDTH characters per line."""
    body = fill(text, indent + 4, WIDTH - 3)
    body[0] = " " * indent + "/-- " + body[0].strip()
    body[-1] = body[-1] + " -/"
    return [l if i == 0 else " " * (indent + 4) + l.strip() for i, l in enumerate(body)]


def checks(info, selected):
    """Pass 2: the lines of Checks.lean. `selected` is one family or None; someAccepted is
    always generated."""
    wanted = {ALWAYS} | ({selected} if selected else set())
    declared = [h.purpose for h in info.handlers]
    undeclared = [p for p in PURPOSES if p not in declared]
    P = info.has_params
    gbinder = " (p : Params)" if P else ""
    gpa = " p" if P else ""
    hp = " honestParams" if P else ""
    tr = info.translator
    names = shape_names(info)
    out = {f: [] for f in FAMILIES}

    def V(e):
        return f"validScriptContext {e} = true"

    def A(e):
        return f"accepts ledgerFuel{hp} {e}"

    def R(e):
        return f"rejects ledgerFuel{hp} {e}"

    def emit(family, name, doc, quant, claim):
        out[family].extend(docstring(doc) + theorem_lines(name, quant, claim, "by blaster") + [""])

    def every(family, name, doc, binders, ctx):
        """A check over every transaction of a purpose: it is rejected."""
        quant = f"∀ {' '.join(binders)}," if binders else ""
        out[family].extend(docstring(doc) + theorem_lines(f"{name}{gbinder}", quant,
                                                          f"¬ accepts ledgerFuel{gpa} ({ctx})", "by blaster") + [""])

    def change(family, shape, doc, x, binders, hyps, changed, verdict, variant=None):
        """A check on a change: for every valid accepted honest transaction (and the binders,
        under `hyps`), if the changed transaction is valid, it has the verdict; then its
        `_applies` check, that such a changed transaction exists."""
        name = f"{family}_{shape}" + (f"_{variant}" if variant else "")
        base = [V(x), A(x)] + hyps
        emit(family, name, doc, "∀ " + " ".join(["p"] + binders) + ",",
             " → ".join(base + [V(changed), verdict]))
        emit(family, f"{name}_applies", f"`{name}` applies: some valid accepted `{shape}` transaction gives "
             "a valid changed transaction, so the check above does not hold only vacuously.",
             "∃ " + ", ∃ ".join(["p"] + binders) + ",", " ∧ ".join(base + [V(changed)]))

    for q in undeclared:
        S = EVERY[q]
        every("otherPurpose", f"otherPurpose_{q}", f"No {NOUN[q]} is accepted: the validator has no {q} handler.",
              ["(r : Data)", f"(t : {S})"], f"{S}.ctx t r")
    for h in info.handlers:
        S = EVERY[h.purpose]
        for sfx, text, bs, term in malformed(tr, h.redeemer_kind, h.redeemer_ctors, 0):
            every("malformedRedeemer", f"malformedRedeemer_{h.purpose}_{sfx}",
                  f"No {NOUN[h.purpose]} is accepted whose redeemer is {text}.", bs + [f"(t : {S})"],
                  f"{S}.ctx t {term}")

    for h in honest_handlers(info):
        spend = h.purpose == "spend"
        mint = h.purpose == "mint"
        for a, _, _ in actions(h, tr):
            s = names[(h.purpose, a)]
            x = f"({s} p)"
            y = f"({s} q)"
            sigs = f"(signatoriesOf {x})"
            outs = f"(outputsOf {x})"
            needs = R(f"(redirectContinuations {x})")
            first = f"(firstContinuation? {x})"
            cont = ("(for transactions that need their outputs back to the script: with those sent to "
                    "another key, they are rejected)")

            emit("someAccepted", f"someAccepted_{s}", f"Some `{s}` transaction is valid in the ledger model "
                 "and accepted.", "∃ p,", f"{V(x)} ∧ {A(x)}")
            emit("someRejected", f"someRejected_{s}", f"Some `{s}` transaction is valid in the ledger model "
                 "and rejected: the validator checks something.", "∃ p,", f"{V(x)} ∧ {R(x)}")

            for other, oindex, ofields in (h.redeemer_ctors or []):
                if short(other) == a:
                    continue
                w = Terms(tr)
                ch = f"(withOwnRedeemer {x} {w.ctor(oindex, ofields)})"
                change("otherRedeemer", s, f"A `{s}` transaction with its redeemer changed to {short(other)} "
                       "is rejected.", x, w.binders, [], ch, R(ch), variant=lower_first(short(other)))
            if spend and info.datum_kind == "constructors" and info.datum_ctors:
                k = len(info.datum_ctors)
                ch = f"(reindexSpendDatum {x} {k})"
                change("spendDatumTag", s, f"A `{s}` transaction whose spent datum has the unknown constructor "
                       f"index {k}, with its fields kept, is rejected.", x, [], [], ch, R(ch))
            if spend:
                ch = f"(withoutSpendDatum {x})"
                change("noSpendDatum", s, f"A `{s}` transaction without a spent datum is rejected (review: "
                       "some validators allow this on purpose).", x, [], [], ch, R(ch))

            ch = f"(withSignatories {x} {sigs}.tail)"
            change("dropSigner", s, f"A `{s}` transaction with its first signatory removed is rejected. Every "
                   "signatory key is a leaf, so this covers removing any one.", x, [], [f"{sigs} ≠ []"], ch, R(ch))
            ch = f"(withSignatories {x} (k :: {sigs}.tail))"
            change("wrongSigner", s, f"A `{s}` transaction with its first signatory replaced by a key not in "
                   "the list is rejected.", x, ["(k : PubKeyHash)"],
                   [f"{sigs} ≠ []", f"{sigs}.contains k = false"], ch, R(ch))
            ch = f"(withSignatories {x} (k :: {sigs}))"
            change("extraSigner", s, f"A `{s}` transaction with an extra signatory, not already in the list, "
                   "added first is still accepted.", x, ["(k : PubKeyHash)"], [f"{sigs}.contains k = false"],
                   ch, A(ch))

            ch = f"(addUnrelatedInputFirst {x} r a)"
            change("unrelatedInput", s, f"A `{s}` transaction with an unrelated input added before its own, "
                   "and an unrelated output, is still accepted.", x, ["(r : TxOutRef)", "(a : Int)"], [], ch, A(ch))

            ch = f"(withOutputs {x} {outs}.reverse)"
            change("reverseOutputs", s, f"A `{s}` transaction with its outputs in reverse order is still "
                   "accepted.", x, [], [], ch, A(ch))
            ch = f"(rotateOutputs {x})"
            change("rotateOutputs", s, f"A `{s}` transaction with its first output moved to the end is still "
                   "accepted.", x, [], [], ch, A(ch))
            ch = f"(addUnrelatedOutput {x} r a)"
            change("unrelatedOutput", s, f"A `{s}` transaction with an unrelated input and output added is "
                   "still accepted.", x, ["(r : TxOutRef)", "(a : Int)"], [], ch, A(ch))

            if spend:
                ch = (f"(changeContinuation {x} (fun o => {{ o with txOutAddress := "
                      f"{{ o.txOutAddress with addressCredential := c }} }}))")
                change("continuationElsewhere", s, f"A `{s}` transaction whose first output back to the script "
                       f"gets another payment credential is rejected {cont}. The staking part is "
                       "continuationStake's.", x, ["(c : Credential)"],
                       [needs, f"{first}.any (fun o => o.txOutAddress.addressCredential == c) = false"], ch, R(ch))
                ch = (f"(changeContinuation {x} (fun o => {{ o with txOutAddress := "
                      f"{{ o.txOutAddress with addressStakingCredential := sc }} }}))")
                change("continuationStake", s, f"A `{s}` transaction whose first output back to the script gets "
                       f"another staking credential is rejected {cont}.", x, ["(sc : Option StakingCredential)"],
                       [needs, f"{first}.any (fun o => o.txOutAddress.addressStakingCredential == sc) = false"],
                       ch, R(ch))
                if info.datum_type is not None and info.datum_kind == "constructors" and info.datum_ctors:
                    w = Terms(tr)
                    w.n = 200
                    good = w.term(info.datum_type)
                    ch = f"(changeContinuation {x} (fun o => {{ o with txOutDatum := .OutputDatum {good} }}))"
                    change("continuationOtherDatum", s, f"A `{s}` transaction whose first output back to the "
                           f"script gets another well-formed datum is rejected {cont}.", x, w.binders,
                           [needs, f"{first}.any (fun o => o.txOutDatum == .OutputDatum {good}) = false"], ch, R(ch))
                    k = len(info.datum_ctors)
                    ch = (f"(changeContinuation {x} (fun o => {{ o with txOutDatum := "
                          f"reindexOutputDatum {k} o.txOutDatum }}))")
                    change("continuationDatumTag", s, f"A `{s}` transaction whose first output back to the "
                           f"script has its datum given the unknown constructor index {k}, with its fields kept, "
                           f"is rejected {cont}.", x, [], [needs], ch, R(ch))
                ch = f"(addJunkFrom {x} r a)"
                change("junkToken", s, f"A `{s}` transaction with a junk token, from a new input, appended to "
                       f"its first output back to the script is rejected {cont}.", x,
                       ["(r : TxOutRef)", "(a : Int)"], [needs], ch, R(ch))
                ch = f"(changeContinuation {x} (fun o => {{ o with txOutReferenceScript := some s }}))"
                change("continuationRefScript", s, f"A `{s}` transaction whose first output back to the script "
                       f"gets a reference script is rejected {cont} (review).", x, ["(s : ByteString)"],
                       [needs], ch, R(ch))

            if mint:
                ch = f"(mintOneMore {x})"
                change("extraMint", s, f"A `{s}` transaction minting one more token under the script's own "
                       "policy is rejected.", x, [], [], ch, R(ch))
                ch = f"(withMint {x} (negateMint (mintOf {x})))"
                change("mintAsBurn", s, f"A `{s}` transaction with its mint turned into a burn, or the other "
                       "way round, is rejected.", x, [], [], ch, R(ch))
            ch = f"(addUnrelatedMint {x} r a)"
            change("unrelatedMint", s, f"A `{s}` transaction with an unrelated token minted and sent to an "
                   "unrelated output is still accepted.", x, ["(r : TxOutRef)", "(a : Int)"], [], ch, A(ch))

            ch = f"(withRange {x} rangeAlways)"
            change("unboundedRange", s, f"A `{s}` transaction with an unbounded validity range is rejected.",
                   x, [], [], ch, R(ch))

            if spend:
                d = f"(addSpendOf {x} {y} r)"
                dq = f"(asSpendOf {d} {y} r)"
                verdict = f"({R(d)} ∨ {R(dq)} ∨ {A(f'(redirectOutputs {d})')} ∨ {A(f'(redirectOutputs {dq})')})"
                change("doubleSatisfaction", s, f"A `{s}` transaction with the input of a second valid accepted "
                       f"`{s}` transaction added, that input's value sent to another key and the outputs "
                       "unchanged: the two script runs do not both accept while both relying on the outputs. One "
                       "run rejects, or one run still accepts with every output redirected.", x,
                       ["q", "r"], [V(y), A(y)], d, verdict)

    applicable = [f for f in FAMILIES if out[f]]
    shown = [f for f in applicable if f in wanted]
    others = [f for f in applicable if f not in wanted]
    missing = [f for f in FAMILIES if not out[f]]
    L = [f"-- Generated by process_blueprint.py from {info.origin}. Do not edit; regenerate.",
         "import Blaster",
         "import Formal.Universal.Properties",
         f"import {info.prefix}.Types",
         f"import {info.prefix}.Tx",
         "",
         "-- Check one proof at a time, in order: Lean prints each result as it",
         "-- comes, and a slow check cannot hold up the ones before it.",
         "set_option Elab.async false",
         "",
         f"namespace {info.prefix}",
         "",
         "open PlutusCore.Data (Data)",
         "open PlutusCore.ByteString (ByteString)",
         "open CardanoLedgerApi.IsData.Class (IsData)",
         "open CardanoLedgerApi.V3 (Address Credential PubKeyHash StakingCredential TxOutRef validScriptContext)",
         "open Formal.Universal.Properties",
         "",
         f"/-! # Universal checks of `{info.head}`",
         "",
         f"Declared handlers: {', '.join(declared)}; " + ("parameters open." if P else "no parameters."),
         ""]
    L += fill(f"Generated here: {', '.join(shown)}.", 0)
    if others:
        L += fill(f"Not generated (run one with the validator's recipe): {', '.join(others)}.", 0)
    if missing:
        L += fill(f"Not applicable to this validator: {', '.join(missing)}.", 0)
    L += ["",
          "`otherPurpose` and `malformedRedeemer` hold over every transaction: everything not named in",
          "the statement is a variable. The other checks start from the shapes in `Tx.lean`: `p` ranges",
          "over every value of a shape's leaves, and Blaster finds which transactions the script accepts.",
          "A check on a change requires its verdict only when the changed transaction is valid in the",
          "ledger model; its `_applies` check shows that such a changed transaction exists.",
          "-/", ""]
    for key, title, fams in SECTIONS:
        present = [f for f in fams if f in shown]
        if present:
            L += [f"/-! ## {title} -/", ""]
            for f in present:
                L += out[f]
    L.append(f"end {info.prefix}")
    return L


def tx_stub(info):
    """The lines of Tx.lean as first written: a skeleton per action, with `sorry` where the
    author fills in the transaction."""
    L = ["-- The honest transactions for the checks in `Checks.lean`: for each action, a shape, that is a",
         "-- transaction with a fixed structure whose leaves are the fields of a structure. Written once by",
         "-- process_blueprint.py as a stub; it is never replaced, so edit it freely.",
         "import CardanoLedgerApi",
         "import Formal.Universal.TxBuilder",
         f"import {info.prefix}.Types",
         "",
         f"namespace {info.prefix}",
         "",
         "open PlutusCore.Data (Data)",
         "open PlutusCore.ByteString (ByteString)",
         "open CardanoLedgerApi.IsData.Class.IsData (toData)",
         "open CardanoLedgerApi.V3 (ScriptContext)",
         "open Formal.Universal.TxBuilder",
         ""]
    if info.has_params:
        L += ["/-- The parameters the honest transactions are for. -/",
              "def honestParams : Params := sorry", ""]
    names = shape_names(info)
    for h in honest_handlers(info):
        ctors = {short(c): (c, fs) for c, _, fs in (h.redeemer_ctors or [])}
        for a, _, _ in actions(h, info.translator):
            s = names[(h.purpose, a)]
            on = "" if a == "any" else f" with redeemer {a}"
            if h.purpose != "spend":
                L += [f"/-- A {NOUN[h.purpose]}{on}: replace `Unit` with a structure of the shape's leaves, and",
                      "    build the transaction from them with the builders in `TxBuilder`. -/",
                      f"def {s} (p : Unit) : ScriptContext := sorry", ""]
                continue
            c, fs = ctors.get(a, (None, None))
            red = f"toData {c}" if c is not None and not fs else "sorry"
            leaves = s.strip("«»")[:1].upper() + s.strip("«»")[1:] + "Leaves"
            L += [f"/-! ## {s.strip('«»')}: a spend{on}. Say here what goes in and out. -/",
                  "",
                  f"/-- The leaves of `{s.strip('«»')}`: add the datum's fields and every other value the",
                  "    transaction is built from. -/",
                  f"structure {leaves} where",
                  "  script : ByteString",
                  "  prevTx : ByteString",
                  "  ownAda : Int",
                  "  fee : Int",
                  "  now : Int",
                  "  txId : ByteString",
                  "",
                  f"def {s} (p : {leaves}) : ScriptContext :=",
                  "  -- The datum: `toData ({ ... } : <the datum type in Types.lean>)`.",
                  "  let own := input p.prevTx 0 (toScript p.script (ada p.ownAda) sorry)",
                  "  Spend.context",
                  "    { own := own",
                  "      outputs := sorry",
                  "      validFrom := p.now",
                  "      fee := p.fee",
                  "      txId := p.txId",
                  f"      redeemer := {red} }}",
                  ""]
    L.append(f"end {info.prefix}")
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blueprint", nargs="?")
    ap.add_argument("validator", nargs="?", help="`module.validator` or `validator`")
    ap.add_argument("--out", default="Formal/Blueprint", help="folder for the Lean files, under Formal/")
    ap.add_argument("--scripts", default="Scripts", help="directory for the .cbor file, as seen by Lean")
    ap.add_argument("--no-checks", action="store_true", help="write Types.lean only (no theorems, no Blaster)")
    ap.add_argument("--cbor-only", action="store_true", help="write only the .cbor file and print its path")
    ap.add_argument("--check", default="", help="the family of checks to generate, e.g. doubleSatisfaction; "
                    f"{ALWAYS} is always generated")
    ap.add_argument("--translation", action="store_true", help="print the translation table and exit")
    a = ap.parse_args()
    if a.translation:
        print(TRANSLATION)
        return
    if not (a.blueprint and a.validator):
        ap.error("a blueprint and a validator are required")
    if a.check and a.check not in FAMILIES:
        sys.exit(f"process_blueprint: unknown check `{a.check}`; choose from {', '.join(FAMILIES)}")
    try:
        bp = json.loads(Path(a.blueprint).read_text())
        if a.cbor_only:
            entries = find_entries(bp, a.validator)
            path = Path(cbor_path_of(entries, a.scripts))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(compiled_code(entries))
            print(path)
            return
        lines, info = generate(bp, a.validator, module_prefix(a.out), a.scripts)
    except (ExtractError, KeyError, json.JSONDecodeError) as e:
        sys.exit(f"process_blueprint: {e}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {"Types.lean": lines + [f"end {info.prefix}"]}
    if not a.no_checks:
        files["Checks.lean"] = checks(info, a.check or None)
    for name, body in files.items():
        (out / name).write_text("\n".join(body) + "\n")
        print(f"wrote {out / name}")
    # Earlier versions wrote the checks into General.lean and Honest.lean.
    for name in ("General.lean", "Honest.lean"):
        old = out / name
        if old.exists() and old.read_text().startswith("-- Generated by process_blueprint.py"):
            old.unlink()
            print(f"removed {old} (replaced by Checks.lean)")
    tx = out / "Tx.lean"
    if not a.no_checks and not tx.exists():
        tx.write_text("\n".join(tx_stub(info)) + "\n")
        print(f"wrote {tx} (a stub: write the honest transactions there)")
    for w in info.warnings:
        print(f"warning: {w}")


if __name__ == "__main__":
    main()
