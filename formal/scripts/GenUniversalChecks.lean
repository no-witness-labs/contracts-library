/-
Universal checks (prototype): generate Blaster obligations from a blueprint, run them, report.

The developer supplies only the compiled validator (plutus.json). This program
reads the blueprint, writes a Base module per validator (the script, the datum
and redeemer shapes, the generic transaction) and one module per check, builds
the check modules in parallel, each with a time limit, and prints a report with
the waivers from universal.json applied. It writes Lean modules from templates,
the way PlutusCoreBlaster's `gen_conformance_tests` writes its test suite.

The transaction is generic: every list in the script context that the shape
covers holds up to two items and Blaster decides which are present (the Bool
"shape" flags); every value is open; every sum type in the datum or redeemer
is a Bool-selected choice between its constructors, and full mode writes one
module per combination of constructors, up to `--max-cases` per check
(`--quick` pins each sum to its first constructor, which is faster and weaker).
The ledger rules (validScriptContext) are a hypothesis on the spend checks.
What the shape does not cover is in Universal/Notes.lean; a PASS holds within
the shape.

Usage, from formal/:
  lake exe universal --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
  lake exe universal --blueprint ../onchain/plutus.json linear_vesting
  lake exe universal --blueprint ../onchain/plutus.json --quick linear_vesting
  lake exe universal --blueprint ../onchain/plutus.json --no-run linear_vesting   (generate only)
Exit code: 1 when any HOLE remains; 2 when any check has no verdict (UNDETERMINED, UNREACHED or
UNKNOWN), which wins over 1; 0 otherwise.
-/
import Lean.Data.Json
import Std.Time
import Std.Sync.Mutex

open Lean (Json)

namespace GenUniversal

/-- A purpose other than spending. Each undeclared purpose is tested on a context that carries
that purpose's witness (the redeemer entry, the withdrawal, the certificate, the vote or the
proposal), so a fallback keyed on the witness is exercised. The checks are unconditional. -/
structure Purpose where
  name : String
  info : String
  key : String
  binders : String
  overrides : String
  consequence : String

def purposes : List Purpose := [
  { name := "mint", info := "(.MintingScript cs)", key := "(.Minting cs)", binders := "(cs : ByteString)",
    overrides := "txInfoMint := [(Data.B cs, Data.Map [(Data.B h.name, Data.I h.qty)])]",
    consequence := "accepted a mint or burn under this script's hash; if the fallback is meant to handle " ++
                   "minting, declare the handler, otherwise anyone can mint" },
  { name := "withdraw", info := "(.RewardingScript (.ScriptCredential cred))", key := "(.Rewarding (.ScriptCredential cred))",
    binders := "(cred : ByteString)", overrides := "txInfoWdrl := [(.ScriptCredential cred, 0)]",
    consequence := "accepted a reward withdrawal for this script's credential; if the fallback is meant to " ++
                   "handle it, declare the handler, otherwise anyone can take the rewards" },
  { name := "publish", info := "(.CertifyingScript 0 (.TxCertRegStaking (.ScriptCredential cred) none))",
    key := "(.Certifying 0 (.TxCertRegStaking (.ScriptCredential cred) none))", binders := "(cred : ByteString)",
    overrides := "txInfoTxCerts := [.TxCertRegStaking (.ScriptCredential cred) none]",
    consequence := "accepted a certificate for this script's credential (register, delegate, retire); " ++
                   "declare the handler or anyone can publish them" },
  { name := "vote", info := "(.VotingScript (.DRepVoter (.ScriptCredential cred)))", key := "(.Voting (.DRepVoter (.ScriptCredential cred)))",
    binders := "(cred : ByteString)", overrides := "txInfoVotes := [(.DRepVoter (.ScriptCredential cred), [])]",
    consequence := "accepted a vote with this script as a DRep; declare the handler or anyone can vote with it" },
  { name := "propose", info := "(.ProposingScript 0 ⟨0, .ScriptCredential cred, Data.I 0⟩)", key := "(.Proposing 0 ⟨0, .ScriptCredential cred, Data.I 0⟩)",
    binders := "(cred : ByteString)", overrides := "txInfoProposalProcedures := [⟨0, .ScriptCredential cred, Data.I 0⟩]",
    consequence := "accepted a governance proposal guarded by this script; declare the handler or anyone can propose" }]

/-- The shape flags (Bool) and open values of the generic transaction. -/
def flags : List String := ["in2", "out2", "out1Script", "out1Foreign", "sig1", "sig2", "mint1", "lowFin"]
def bytes : List String := ["s1", "s2", "payee", "payee2", "policy", "name"]
def ints : List String := ["inLov", "inLov2", "outLov", "outLov2", "qty", "lo", "fee"]
/-- No output on chain holds less: 4,310 lovelace per byte times the 160-byte overhead (CIP-55).
Universal claims assume only this, so a PASS covers every amount the ledger allows. -/
def ledgerFloor : Nat := 689600
/-- Witnesses of existence claims hold at least 1 ada everywhere, so they are not dust. Stricter
than the ledger, and still not exact: an output with a datum and tokens can need more. -/
def witnessMin : Nat := 1000000

structure Config where
  quick : Bool := false
  noValidity : Bool := false
  noPrep : Bool := true
  prepSteps : Nat := 60000
  /-- Seconds per module, wall clock; a slower module is stopped and reports UNDETERMINED. -/
  timeout : Nat := 600
  /-- Modules per check in full mode; sums that do not fit stay open inside each module. -/
  maxCases : Nat := 16

/-! ## Data terms with the blueprint's shape -/

/-- One sum type: n constructors chosen by n - 1 nested Bool flags. The first flag picks the
first constructor, the next the second, and all false the last. `nested` holds, per constructor,
the sums inside its fields, which matter only when that constructor is chosen. -/
inductive Choice where
  | mk (title : String) (ctors : Array String) (flags : Array String) (nested : Array (Array Choice))

instance : Inhabited Choice := ⟨.mk "" #[] #[] #[]⟩

def Choice.title : Choice → String | .mk t _ _ _ => t
def Choice.ctors : Choice → Array String | .mk _ c _ _ => c
def Choice.flags : Choice → Array String | .mk _ _ f _ => f
def Choice.nested : Choice → Array (Array Choice) | .mk _ _ _ n => n

/-- The hypotheses that pick constructor k. -/
def Choice.select (ch : Choice) (k : Nat) : List String :=
  (ch.flags.toList.take k).map (fun f => s!"h.{f} = false") ++
    (if k < ch.flags.size then [s!"h.{ch.flags[k]!} = true"] else [])

structure GenState where
  /-- Every leaf name starts with it; it holds "_", so no fixed field collides. -/
  pfx : String
  /-- How the report names this term's sums, e.g. "output ". -/
  label : String := ""
  binders : Array (String × String) := #[]
  /-- The outermost sums of the terms built so far. -/
  choices : Array Choice := #[]
  n : Nat := 0

abbrev GenM := StateT GenState (Except String)

def field? (j : Json) (k : String) : Option Json := (j.getObjVal? k).toOption
def str? (j : Json) (k : String) : Option String := (field? j k).bind fun v => v.getStr?.toOption
def arr? (j : Json) (k : String) : Option (Array Json) := (field? j k).bind fun v => v.getArr?.toOption
/-- A missing or empty string gives the default. -/
def orElse (o : Option String) (d : String) : String :=
  match o with
  | some s => if s.isEmpty then d else s
  | none => d
def indexStr (j : Json) : String := ((field? j "index").map (·.compress)).getD "None"
def refKey (r : String) : String := (r.splitOn "/").getLast!
def resolve (defs : Json) (r : String) : Except String Json :=
  match field? defs ((refKey r).replace "~1" "/") with
  | some d => .ok d
  | none => .error s!"the blueprint has no definition {r}"

def fresh (ty hint : String) : GenM String := do
  let s ← get
  let name := s!"{s.pfx}{hint}{s.n + 1}"
  set { s with n := s.n + 1, binders := s.binders.push (name, ty) }
  return s!"h.{name}"

/-- A Data term with the blueprint's shape: symbolic leaves, a Bool choice per sum type. -/
partial def gen (defs : Json) (quick : Bool) (schema : Json) (hint : String := "x") (title : Option String := none) :
    GenM String := do
  if let some r := str? schema "$ref" then
    if refKey r == "Data" then
      let leaf ← fresh "Int" "any"
      return s!"Data.I {leaf}"  -- any Data: an open integer stands in
    let d ← resolve defs r
    return ← gen defs quick d hint title
  if let some alts := arr? schema "anyOf" then
    if quick || alts.size == 1 then
      return ← gen defs quick alts[0]! hint title  -- quick mode, or nothing to choose
    let outer := (← get).choices
    let mut branches : Array String := #[]
    let mut nested : Array (Array Choice) := #[]
    for c in alts do
      modify fun s => { s with choices := #[] }
      let t ← gen defs quick c hint title
      branches := branches.push t
      nested := nested.push (← get).choices
    modify fun s => { s with choices := outer }
    let mut fs : Array String := #[]
    let mut term := branches.back!
    for k in (List.range (branches.size - 1)).reverse do
      let flag ← fresh "Bool" "c"
      fs := #[flag.drop 2] ++ fs
      term := s!"(if {flag} then {branches[k]!} else {term})"
    let ctors := alts.map fun c => orElse (str? c "title") (indexStr c)
    let label := (← get).label
    modify fun s => { s with choices := s.choices.push (.mk (label ++ title.getD hint) ctors fs nested) }
    return term
  match str? schema "dataType" with
  | some "constructor" =>
    let mut parts : Array String := #[]
    for f in (arr? schema "fields").getD #[] do
      let ft := (str? f "title").filter (!·.isEmpty)
      -- a field's title is its path from the datum, e.g. owner.payment_credential, so the report can name it
      let path := match title, ft with
        | some t, some x => some s!"{t}.{x}"
        | _, _ => ft <|> title
      parts := parts.push (← gen defs quick f ((orElse ft hint).take 8) path)
    let args := ", ".intercalate parts.toList
    return s!"Data.Constr {indexStr schema} [{args}]"
  | some "bytes" => return s!"Data.B {← fresh "ByteString" hint}"
  | some "integer" => return s!"Data.I {← fresh "Int" hint}"
  | some "list" =>
    match field? schema "items" with
    | some items => return s!"Data.List [{← gen defs quick items hint title}]"  -- one element (bounded shape)
    | none => return "Data.List []"
  | some "map" => return "Data.Map []"
  | _ => return s!"Data.I {← fresh "Int" "any"}"

/-- One (name, term, constructor count, sums) per top-level redeemer constructor; else one unnamed
term. Each action keeps its own sums, so they split only that action's checks. -/
def variants (defs : Json) (quick : Bool) (schema : Json) (hint : String) :
    GenM (Array (String × String × Nat × Array Choice)) := do
  let schema ← match str? schema "$ref" with
    | some r => if refKey r != "Data" then resolve defs r else pure schema
    | none => pure schema
  let ctors := (arr? schema "anyOf").filter fun cs => cs.all fun c => str? c "dataType" == some "constructor"
  let mut out := #[]
  for c in ctors.getD #[schema] do
    modify fun s => { s with choices := #[] }
    let term ← gen defs quick c hint
    let name := if ctors.isSome then orElse (str? c "title") s!"c{indexStr c}" else ""
    out := out.push (name, term, (ctors.map (·.size)).getD 0, (← get).choices)
  modify fun s => { s with choices := #[] }
  return out

/-! ## Rendering -/

/-- One Lean declaration, kept in parts so a case adds its hypotheses without editing text.
`falsify` states a universal claim Blaster must falsify: its counterexample is the witness. -/
structure Decl where
  name : String
  doc : String
  claim : String
  /-- Lines of hypotheses, each joined with →. -/
  hyps : List String := []
  /-- Extra binders after `h`, e.g. "∀ m : Int,". -/
  binders : String := ""
  falsify : Bool := false
  /-- Names the module when a check has more than one declaration. -/
  part : String := ""

/-- The declaration for one case: the case's hypotheses first, then the check's own. -/
def render (timeout : Nat) (d : Decl) (caseHyps : List String) (suffix : String) : List String :=
  let name := d.name ++ suffix
  let head := "∀ h : Holes," ++ (if d.binders.isEmpty then "" else s!" {d.binders}")
  let lines := ((if caseHyps.isEmpty then [] else [" → ".intercalate caseHyps]) ++ d.hyps).map fun l => s!"    {l} →"
  if d.falsify then
    [s!"/-- {d.doc} -/", s!"def {name} : Prop := {head}"] ++ lines ++ [s!"    {d.claim}",
     "-- A solver timeout is a warning on this command; as an error it fails the build.",
     "set_option warningAsError true in",
     s!"#blaster (timeout: {timeout}) (solve-result: 1) [{name}]"]
  else
    [s!"/-- {d.doc} -/", s!"theorem {name} : {head}"] ++ lines ++ [s!"    {d.claim} := by",
     s!"  blaster (timeout: {timeout})"]

def opens : List String := [
  "open PlutusCore.UPLC.Term (Program)",
  "open PlutusCore.ByteString (ByteString)",
  "open PlutusCore.Data (Data)",
  "open CardanoLedgerApi.IsData.Class (IsData)",
  "open CardanoLedgerApi.V3 (Address ScriptContext ScriptInfo ScriptPurpose TxInfo TxInInfo TxOut Value)",
  "open CardanoLedgerApi.V1.Time (POSIXTimeRange after everything)",
  "open PlutusCore.UPLC.Utils (isSuccessful isUnsuccessful)"]

def headerNotes (quick : Bool) (name : String) : String := "\n".intercalate [
  "/-!",
  s!"# Universal checks for `{name}`",
  "",
  "Security checks that apply to any compiled validator, instantiated on this one from its",
  "blueprint. Nothing here was written by the validator's author. Design notes, limits and the",
  "review history are in `Universal/Notes.lean`; this header is the short form.",
  "",
  "## What is open",
  "",
  "Every open value is a field of the `Holes` structure below; each check quantifies over one",
  "`h : Holes` and pins the fields it needs with hypotheses. The transaction is composed from the",
  "builders in `Universal.Harness`.",
  "",
  "- Shape flags: a second script input, a second output, where the first output goes (own script,",
  "  a key, another script), two signers, one minted asset, a finite or absent lower validity bound.",
  "- Every value: lovelace amounts, fee, signers, policy, asset name, quantity, times.",
  "- The datum of the own input and the datum of the continuing output, each with the blueprint's",
  "  shape, independent leaves and a Bool choice per sum type" ++
    (if quick then " (pinned to the first constructor: quick mode)" else "") ++ ".",
  "- One redeemer per declared action, same treatment; any `Data` leaf is an open integer.",
  "",
  "## What is not in the shape",
  "",
  "No reference inputs, no withdrawals on spends, no certificates, no datum hashes, no tokens on",
  "inputs, at most two of each list, exactly one item in each list inside a datum, no entries in a",
  "map inside a datum, no finite upper validity bound. A PASS holds within the shape; a contract",
  "whose accept path needs one of these shows UP-000 as REVIEW and its other checks as UNREACHED.",
  "The script hash is a placeholder, used consistently.",
  "",
  "## Reading the verdicts",
  "",
  "`#blaster (solve-result: 1)` means the stated universal claim must be falsified: the counterexample",
  "is a working transaction Blaster found. A `theorem ... := by blaster` must hold. `valid` is the",
  "ledger rule set from CardanoLedgerApi. `ledgerFloor` is the minimum the ledger puts on every output,",
  "so a theorem that assumes only that covers every amount the chain allows; `realistic` asks 1 ada of",
  "every amount, so a witness is not dust. A Blaster `Valid` is an SMT verdict with no proof term, as",
  "everywhere in this repository. One module per check and case, so lake builds them in parallel.",
  "-/"]

/-! ## Cases -/

/-- Every combination of constructors, as (hypotheses, labels). `deep` also splits the sums
nested inside a chosen constructor; otherwise those stay open inside the module. -/
partial def combinations (chs : List Choice) (deep : Bool) : List (List String × List String) :=
  chs.foldl (init := [([], [])]) fun result ch =>
    let opts := (List.range ch.ctors.size).flatMap fun k =>
      let subs := if deep then combinations ch.nested[k]!.toList deep else [([], [])]
      subs.map fun (hs, ls) => (ch.select k ++ hs, s!"{ch.title} is {ch.ctors[k]!}" :: ls)
    result.flatMap fun (h1, l1) => opts.map fun (h2, l2) => (h1 ++ h2, l1 ++ l2)

/-- At most `maxCases` cases: every combination when they fit, else the outermost sums only, as
many as fit, in order. A sum left out is still an open choice inside each module, so every
combination stays covered, in fewer and harder modules. -/
def split (maxCases : Nat) (chs : List Choice) : List (List String × List String) :=
  let cases := combinations chs true
  if cases.length ≤ maxCases then cases
  else
    let kept := chs.foldl (init := []) fun kept ch =>
      if (combinations (kept ++ [ch]) false).length ≤ maxCases then kept ++ [ch] else kept
    combinations kept false

/-- One module to build: its check, its case, and what it must show. -/
structure Obligation where
  id : String
  group : String
  caseLabel : String
  caseKey : List String
  module : String
  title : String
  expect : String
  severity : String
  action : String
  defaultOn : Bool := true
  consequence : String
  fields : Array String
deriving Inhabited

/-- What the generator writes for one validator. -/
structure Generated where
  mod : String
  base : String
  modules : Array (String × String)
  obligations : Array Obligation

/-- Every module and obligation for one validator. `choices` and `outChoices` are the outermost
sums of the input datum and of the continuing output's datum. -/
def generate (cfg : Config) (name hexCode : String) (declared : List String) (datumTerm outDatumTerm : String)
    (redeemers : Array (String × String × Nat × Array Choice)) (leaves : Array (String × String))
    (choices outChoices : List Choice) : Generated := Id.run do
  let mod := name.capitalize
  let ns := s!"Universal.Demo.{mod}"
  -- #prep_uplc declares its name outside any namespace, so two contracts must not share it:
  -- a file importing both would fail. Name it after the validator.
  let camel := String.join ((name.splitOn "_").map String.capitalize)
  let prepId := s!"universal{camel}Prepared"
  let undeclared := purposes.filter fun p => !declared.contains p.name
  let fields := (flags.map (·, "Bool")).toArray ++ leaves ++ (bytes.map (·, "ByteString")).toArray ++
    (ints.map (·, "Int")).toArray
  let fieldNames := fields.map (·.1)

  -- ---- Base module: the script, the holes, the transaction composed from the harness ----
  let mut b := [s!"-- Generated by `lake exe universal` from the blueprint entry `{name}`. Do not edit; regenerate.",
    "import Blaster", "import PlutusCore.UPLC", "import CardanoLedgerApi.V3", "import CardanoLedgerApi.V1.Time",
    "import PlutusCore.UPLC.PreProcess", "import Formal.Common", "import Universal.Harness", "",
    headerNotes cfg.quick name, "", s!"namespace {ns}", ""] ++ opens ++ ["open Universal.Harness", ""]
  -- The compiled code sits in this file, so a new build of the contract changes the file and lake
  -- rebuilds every check; a separate script file would leave the old build in the cache.
  b := b ++ ["/-- The compiled validator, as the blueprint holds it. -/",
    "abbrev script : PlutusCore.UPLC.PlutusScript.PlutusScript :=",
    s!"  ⟨.PlutusV3, singleCborEncodedScriptFromHexM \"{hexCode}\"⟩"]
  if cfg.noPrep then
    b := b ++ ["def validator : Program := script.script",
      "def accepts (ctx : ScriptContext) : Prop := Formal.Common.validatorAccepts ctx validator",
      "def rejects (ctx : ScriptContext) : Prop := Formal.Common.validatorRejects ctx validator"]
  else
    b := b ++ ["def allInputs (ctx : ScriptContext) : List PlutusCore.UPLC.Term.Term := [CardanoLedgerApi.IsData.Class.toTerm ctx]",
      s!"#prep_uplc {prepId} script allInputs {cfg.prepSteps}",
      s!"def accepts (ctx : ScriptContext) : Prop := isSuccessful ({prepId}.prop ctx)",
      s!"def rejects (ctx : ScriptContext) : Prop := isUnsuccessful ({prepId}.prop ctx)"]
  if cfg.noValidity then
    b := b ++ ["def valid (_ctx : ScriptContext) : Prop := True"]
  else
    b := b ++ ["/-- Ledger rules (CardanoLedgerApi): a counterexample must be a transaction the chain would accept. -/",
      "def valid (ctx : ScriptContext) : Prop := CardanoLedgerApi.V3.Contexts.validScriptContext ctx = true"]
  b := b ++ ["", "/-- Every open value of a spend of this validator, one field each. Blaster fills them. -/",
    "structure Holes where"] ++ (fields.toList.map fun (n, t) => s!"  {n} : {t}")
  let floor := s!"{ledgerFloor}"
  let wmin := s!"{witnessMin}"
  b := b ++ ["", "/-- The ledger's minimum on every output, which the model does not enforce: 4,310 lovelace per byte",
    "    times the 160-byte overhead (CIP-55). Every real transaction meets it. -/",
    "def ledgerFloor (h : Holes) : Prop :=",
    s!"  {floor} ≤ h.inLov ∧ {floor} ≤ h.inLov2 ∧ {floor} ≤ h.outLov ∧ {floor} ≤ h.outLov2",
    "/-- At least 1 ada everywhere: what a witness must hold, so it is not dust. -/",
    "def realistic (h : Holes) : Prop :=",
    s!"  {wmin} ≤ h.inLov ∧ {wmin} ≤ h.inLov2 ∧ {wmin} ≤ h.outLov ∧ {wmin} ≤ h.outLov2",
    "",
    "def own : ByteString := \"fake_script_hash_28bytes!!!!\"",
    "def ownRef : CardanoLedgerApi.V3.TxOutRef := ⟨\"txid_placeholder_32bytes!!!!!!!!\", 0⟩",
    "def ref2 : CardanoLedgerApi.V3.TxOutRef := ⟨\"txid_placeholder_32bytes!!!!!!!!\", 1⟩",
    "",
    "/-- Datum of the script's own input, with the blueprint's shape; sums chosen by flags in `h`. -/",
    s!"def datum (h : Holes) : Data := {datumTerm}",
    "/-- Datum of the continuing output: same shape, its own fields and flags, so it may differ from the input's. -/",
    s!"def datumOut (h : Holes) : Data := {outDatumTerm}",
    "/-- Redeemers with the blueprint's shape, one per constructor. -/"]
  for (rname, rterm, _, _) in redeemers do
    b := b ++ [s!"def redeemer{rname} (h : Holes) : Data := {rterm}"]
  b := b ++ ["",
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
    "", s!"end {ns}"]
  let base := "\n".intercalate b ++ "\n"

  -- ---- One module per check, declaration and case ----
  -- Full mode splits a check into one module per combination of constructors: each choice is a
  -- hypothesis, so each module explores one combination. The hypotheses go in as parts of the
  -- declaration (`render`), never by editing rendered text.
  let check := fun (modName oid title expect consequence severity action : String) (decls : List Decl)
      (sums : List Choice) => Id.run do
    let mut out : Array (String × String × Obligation) := #[]
    for (hyps, labels) in split cfg.maxCases sums do
      -- h.d_c3 = true -> _d_c3t
      let suffix := String.join (hyps.map fun x => let ws := x.splitOn " "; s!"_{(ws.head!).drop 2}{(ws.getLast!).take 1}")
      let label := ", ".intercalate labels
      for d in decls do
        let part := if d.part.isEmpty then "" else s!"_{d.part}"
        let module := s!"{ns}.{modName}{part}{suffix}"
        let desc := ", ".intercalate ([d.part.replace "_" " ", label].filter (!·.isEmpty))
        let shown := if desc.isEmpty then "" else s!" ({desc})"
        let lines := [s!"-- Generated by `lake exe universal`: {oid} for `{name}`{shown}. Do not edit; regenerate.",
          s!"import {ns}.Base", "", s!"namespace {ns}", ""] ++ opens ++ ["open Universal.Harness", ""] ++
          render cfg.timeout d hyps suffix ++ ["", s!"end {ns}"]
        let id := oid ++ (if d.part.isEmpty then "" else s!":{d.part}") ++ (if suffix.isEmpty then "" else s!"#{suffix}")
        out := out.push (module, "\n".intercalate lines ++ "\n",
          { id, group := oid, caseLabel := desc, caseKey := hyps, module, title, expect, severity, action,
            consequence, fields := fieldNames })
    return out
  let add := fun (acc : Array (String × String) × Array Obligation) (xs : Array (String × String × Obligation)) =>
    (acc.1 ++ xs.map (fun (m, s, _) => (m, s)), acc.2 ++ xs.map (·.2.2))

  let typedRedeemer := !(redeemers[0]!.1).isEmpty
  let nCtors := redeemers[0]!.2.2.1
  let pin := "h.out1Foreign = false"  -- only UP-011 lets the output go to another script
  let datums := choices ++ outChoices
  let mut acc : Array (String × String) × Array Obligation := (#[], #[])

  for (rname, _, _, rsums) in redeemers do
    let tag := if rname.isEmpty then "" else s!"/{rname}"
    let act := if rname.isEmpty then "spend" else rname
    let sums := datums ++ rsums.toList  -- every spend check of an action splits on the same sums
    let c := s!"ctx h (redeemer{rname} h)"
    acc := add acc <| check s!"UP000_{act}" s!"UP-000{tag}" s!"sanity: action `{act}` is reachable" "Falsified"
      ("no spend of the generated shapes is accepted: funds locked, or the action needs something the " ++
       "shape lacks (reference inputs, withdrawals, tokens on inputs, a third output)") "review" act
      [{ name := s!"alwaysRejects{rname}", doc := s!"UP-000{tag}: is any realistic valid spend with this action accepted? Blaster must FALSIFY this.",
         claim := s!"rejects ({c})", hyps := [pin, s!"valid ({c}) → realistic h"], falsify := true }] sums
    acc := add acc <| check s!"UP004_{act}" s!"UP-004{tag}" s!"action `{act}` is not always accepted" "Falsified"
      "this action accepts every realistic valid transaction of the generated shapes: an always-true branch"
      "hole" act
      [{ name := s!"alwaysAccepts{rname}", doc := s!"UP-004{tag}: is any realistic valid spend with this action rejected? Blaster must FALSIFY this.",
         claim := s!"accepts ({c})", hyps := [pin, s!"valid ({c}) → realistic h"], falsify := true }] sums
    acc := add acc <| check s!"UP002_{act}" s!"UP-002{tag}" s!"action `{act}` rejects a spend with no signatories" "Valid"
      "this action can be spent without any signature; by design only for scripts authenticated another way"
      "review" act
      [{ name := s!"up002_{act}", doc := s!"UP-002{tag}: a valid spend with no signatories is rejected (waive it for permissionless scripts).",
         claim := s!"rejects ({c})", hyps := [s!"h.sig1 = false → h.sig2 = false → {pin}", s!"valid ({c}) → ledgerFloor h"] }] sums
    let atCtx := s!"ctx \{ h with out1Script := true } (redeemer{rname} h)"
    let moved := s!"ctx \{ h with out1Script := false } (redeemer{rname} h)"
    -- `payee` names the other script when the output moves to one; without `≠ own` the solver
    -- could name the own script, and the moved output would equal the original.
    acc := add acc <| check s!"UP011_{act}" s!"UP-011{tag}" s!"action `{act}`: moving the continuing output is rejected" "Valid"
      ("the same spend was accepted with the output moved elsewhere; confirm that paying out is intended " ++
       "for this action and this case, otherwise the datum can be hijacked") "review" act
      [{ name := s!"up011_{act}", doc := s!"UP-011{tag}: a spend accepted with its output back at the script, whatever datum that output carries within the shape, is rejected once that output moves to a key or another script.",
         claim := s!"accepts ({atCtx}) → rejects ({moved})",
         hyps := ["h.payee ≠ own", s!"valid ({atCtx}) → valid ({moved}) → ledgerFloor h"] }] sums

  if typedRedeemer then
    acc := add acc <| check "UP005" "UP-005" "rejects a malformed redeemer" "Valid"
      "a redeemer that matches no declared action is accepted" "hole" ""
      [{ name := "up005_integer_redeemer", doc := "UP-005: a valid spend whose redeemer is an integer is rejected.",
         claim := "rejects (ctx h (Data.I m))", hyps := [pin, "valid (ctx h (Data.I m)) → ledgerFloor h"],
         binders := "∀ m : Int,", part := "integer_redeemer" },
       { name := "up005_unknown_constructor", doc := "UP-005: a valid spend whose redeemer is a constructor the type lacks is rejected.",
         claim := "rejects (ctx h (Data.Constr k []))", hyps := [s!"{nCtors} ≤ k → {pin}", "valid (ctx h (Data.Constr k [])) → ledgerFloor h"],
         binders := "∀ k : Nat,", part := "unknown_constructor" }] datums

  for p in undeclared do
    acc := add acc <| check s!"UP001_{p.name}" s!"UP-001/{p.name}" s!"rejects undeclared purpose `{p.name}`" "Valid" p.consequence "hole" ""
      [{ name := s!"up001_{p.name}", doc := s!"UP-001/{p.name}: the script declares no `{p.name}` handler, so it must reject that purpose, even with the purpose's witness present.",
         claim := s!"rejects (otherCtx {p.info} {p.key} (Data.I rp)\n      \{ txOf h (datum h) (Data.I rp) with {p.overrides} })",
         hyps := [pin], binders := s!"∀ (rp : Int) {p.binders}," }] choices
  return { mod, base, modules := acc.1, obligations := acc.2 }

/-! ## Reading Blaster's output -/

def isPathChar (c : Char) : Bool := c.isAlphanum || c == '_' || c == '.' || c == '/' || c == '-'

/-- The file of the first `<file>.lean:<line>:<col>:` in a line, as lake prints a message's location. -/
def locPath? (line : String) : Option String := Id.run do
  let parts := line.splitOn ".lean:"
  for i in [0:parts.length - 1] do
    let stem := String.mk (parts[i]!.toList.reverse.takeWhile isPathChar).reverse
    let after := parts[i+1]!.toList
    let d1 := after.takeWhile Char.isDigit
    let rest := after.drop d1.length
    if !stem.isEmpty && !d1.isEmpty && rest.head? == some ':' then
      let d2 := (rest.drop 1).takeWhile Char.isDigit
      if !d2.isEmpty && (rest.drop (1 + d2.length)).head? == some ':' then
        return some (stem ++ ".lean")
  return none

/-- A `- name: value` entry after a location, as Blaster prints each open variable. -/
def entry? (line : String) : Option (String × String) := Id.run do
  let cs := line.toList
  for i in [0:cs.length] do
    if cs[i]! == ':' then
      let rest := (cs.drop (i + 1)).dropWhile Char.isWhitespace
      if rest.take 2 == ['-', ' '] then
        let w := (rest.drop 2).takeWhile fun c => c.isAlphanum || c == '_'
        let after := rest.drop (2 + w.length)
        if !w.isEmpty && after.take 2 == [':', ' '] then
          return some (String.mk w, String.mk (after.drop 2))
  return none

/-- Blaster's messages (Blaster/Smt/Env.lean), and what each says about the claim as stated. A
theorem that comes back undetermined is left with an unsolved goal and no Blaster message of its own. -/
def verdicts : List (String × String) := [("❌ Unexpected Valid", "Valid"), ("✅ Valid", "Valid"),
  ("✅ Expected Falsified", "Falsified"), ("❌ Falsified", "Falsified"),
  ("✅ Expected Undetermined", "Undetermined"), ("⚠️ Undetermined", "Undetermined"),
  ("unsolved goals", "Undetermined")]

/-- Split a printed Lean application into its top-level arguments: an atom, a string literal, or a
parenthesised term, whatever line breaks Lean put inside them. -/
def terms (text : String) : List String := Id.run do
  let cs := text.toList.toArray
  let n := cs.size
  let skipString := fun (i : Nat) => Id.run do
    let mut j := i + 1
    while j < n && cs[j]! != '"' do
      j := j + (if cs[j]! == '\\' then 2 else 1)
    return j + 1
  let mut out : Array String := #[]
  let mut i := 0
  while i < n do
    if cs[i]!.isWhitespace then
      i := i + 1
      continue
    let start := i
    if cs[i]! == '(' then
      let mut depth : Int := 0
      while i < n do
        if cs[i]! == '"' then
          i := skipString i
          continue
        if cs[i]! == '(' then depth := depth + 1
        else if cs[i]! == ')' then depth := depth - 1
        i := i + 1
        if depth == 0 then break
    else if cs[i]! == '"' then
      i := skipString i
    else
      while i < n && !cs[i]!.isWhitespace && cs[i]! != '(' && cs[i]! != ')' do
        i := i + 1
    out := out.push (String.mk (cs.extract start (min i n)).toList)
  return out.toList

/-- Blaster prints one `- name: value` line per open variable; a value Lean wraps continues on the
following unlocated lines. A `Holes` value is split into its fields, in declaration order. -/
def parseWitness (msgs : List String) (fieldNames : Array String) : List String := Id.run do
  let mut entries : Array (Option (String × String)) := #[]
  for line in msgs do
    if (locPath? line).isSome then
      entries := entries.push (entry? line)
    else if let some (some (n, v)) := entries.back? then
      entries := entries.pop.push (some (n, v ++ " " ++ line.trim))
  let clean := fun (v : String) => v.replace "PlutusCore.ByteString.PlutusCore.ByteStringInternal.ByteString.mk " ""
  let mut witness : List String := []
  for e in entries do
    let some (name, value) := e | continue
    let value := value.trim
    let args := if value.startsWith "(" && value.endsWith ")" then terms ((value.drop 1).dropRight 1) else []
    if args.head?.any (·.endsWith ".Holes.mk") then
      witness := witness ++ ((fieldNames.toList.zip args.tail).map fun (f, v) => s!"{f} = {clean v}")
    else
      let shown := if value.startsWith "$" then "any value" else clean value
      witness := witness ++ [s!"{name} = {shown}"]
  return witness

/-! ## Running -/

def lakeCmd (nixShell : String) (module : String) : String × Array String :=
  if nixShell.isEmpty then ("lake", #["build", module])
  else ("nix", #["develop", nixShell, "-c", "lake", "build", module])

/-- Build one module in its own process group, so the time limit stops Lean and Z3 together.
Returns the output and whether the time limit stopped it. -/
def buildOne (formal : System.FilePath) (nixShell : String) (timeout : Nat) (module : String) : IO (String × Bool) := do
  let (cmd, args) := lakeCmd nixShell module
  let child ← IO.Process.spawn { cmd, args, cwd := formal, stdin := .null, stdout := .piped, stderr := .piped, setsid := true }
  let out ← IO.asTask (prio := .dedicated) child.stdout.readToEnd
  let err ← IO.asTask (prio := .dedicated) child.stderr.readToEnd
  let deadline := (← IO.monoMsNow) + timeout * 1000
  let mut stopped := false
  repeat
    if (← child.tryWait).isSome then break  -- exited, and already reaped
    if (← IO.monoMsNow) ≥ deadline then
      child.kill
      let _ ← child.wait
      stopped := true
      break
    IO.sleep 200
  return ((← IO.ofExcept out.get) ++ (← IO.ofExcept err.get), stopped)

/-- Run `f` on every item, `jobs` at a time, and keep the results in order. -/
def runPool {α β : Type} [Inhabited α] [Inhabited β] (jobs : Nat) (items : Array α) (f : α → IO β) : IO (Array β) := do
  let next ← Std.Mutex.new 0
  let worker : IO (Array (Nat × β)) := do
    let mut done := #[]
    repeat
      let i ← next.atomically (modifyGet fun i => (i, i + 1))
      if i ≥ items.size then break
      done := done.push (i, ← f items[i]!)
    return done
  let tasks ← (List.range (max 1 jobs)).mapM fun _ => IO.asTask (prio := .dedicated) worker
  let mut results := Array.replicate items.size default
  for t in tasks do
    for (i, r) in ← IO.ofExcept t.get do
      results := results.set! i r
  return results

structure Result where
  ob : Obligation
  verdict : String
  status : String
  witness : String
deriving Inhabited

/-- Build the Base module, then every check module in parallel, one verdict per module. `none`
when the Base module does not build; the log comes back either way. -/
def runAndParse (formal : System.FilePath) (cfg : Config) (base : String) (obligations : Array Obligation)
    (nixShell : String) (jobs : Nat) : IO (Option (Array Result) × String) := do
  let (cmd, args) := lakeCmd nixShell base
  let proc ← IO.Process.output { cmd, args, cwd := formal }
  let baseLog := proc.stdout ++ proc.stderr
  if proc.exitCode != 0 then return (none, baseLog)
  let outputs ← runPool jobs obligations fun o => buildOne formal nixShell cfg.timeout o.module
  let mut report := #[]
  let mut raw := baseLog
  for (o, (out, stopped)) in obligations.zip outputs do
    raw := raw ++ out ++ (if stopped then s!"\n[stopped after {cfg.timeout} s: {o.module}]\n" else "")
    let path := (o.module.replace "." "/") ++ ".lean"
    let mut msgs : Array String := #[]
    let mut current := false
    for line in out.splitOn "\n" do
      match locPath? line with
      | some p =>
        current := (p.dropWhile (fun c => c == '.' || c == '/')).endsWith path
        if current then msgs := msgs.push line
      | none =>
        if current && line.startsWith "  " then msgs := msgs.push line  -- a counterexample value on its own line
        else current := false
    let text := "\n".intercalate msgs.toList
    let found := (verdicts.find? fun (marker, _) => (text.splitOn marker).length > 1).map (·.2)
    let verdict := if stopped then "Undetermined"
      else found.getD (if (text.splitOn "error").length > 1 then "Error" else "Unknown")  -- never trust silence
    let status := if verdict == o.expect then "PASS"
      else if verdict == "Valid" || verdict == "Falsified" then "FAIL"
      else if verdict == "Undetermined" then "UNDETERMINED" else "UNKNOWN"
    report := report.push { ob := o, verdict := if stopped then "time limit" else verdict, status,
                            witness := ", ".intercalate (parseWitness msgs.toList o.fields) }
  return (some report, raw)

/-- One line per check. -/
structure Folded where
  r : Result
  id : String
  status : String
  cases : String := ""
  failing : List String := []
  stopped : List String := []

/-- One line per check. An existence claim (UP-000, UP-004) holds if one case shows it; a universal
claim holds only if every reached case does. A case with no accepted spend for its action is
UNREACHED and proves nothing, so the line names the cases it covers. -/
def foldCases (report0 : Array Result) : Array Folded := Id.run do
  -- Only a proved "always rejects" makes a case unreached; a UP-000 with no verdict decides nothing.
  let unreached := report0.filter (fun r => r.ob.group.startsWith "UP-000" && r.status == "FAIL")
    |>.map fun r => (r.ob.action, r.ob.caseKey)
  let report := report0.map fun r =>
    if r.status == "PASS" && r.ob.expect == "Valid" && !r.ob.action.isEmpty && unreached.contains (r.ob.action, r.ob.caseKey)
    then { r with status := "UNREACHED" } else r
  let mut groups : Array String := #[]
  for r in report do
    if !groups.contains r.ob.group then groups := groups.push r.ob.group
  let mut folded := #[]
  for gid in groups do
    let rs := (report.filter (·.ob.group == gid)).toList
    let statuses := rs.map (·.status)
    let mut pick : Option Result := none
    let mut status := ""
    if rs.head!.ob.expect == "Falsified" then
      pick := rs.find? (·.status == "PASS")
      status := if pick.isSome then "PASS"
        else if statuses.all (· == "FAIL") then "FAIL"
        else (statuses.find? fun t => t != "PASS" && t != "FAIL").getD "UNKNOWN"
    else
      pick := rs.find? (·.status == "FAIL")
      status := if pick.isSome then "FAIL"
        else if statuses.all (fun t => t == "PASS" || t == "UNREACHED") then
          (if statuses.contains "PASS" then "PASS" else "UNREACHED")
        else (statuses.find? fun t => t != "PASS" && t != "UNREACHED").getD "UNKNOWN"
    let chosen := pick.getD ((rs.find? (·.status == status)).getD rs.head!)
    let count := fun s => (statuses.filter (· == s)).length
    let cases := if rs.length > 1 then
      s!"{count "PASS"} of {rs.length} cases pass" ++ (if statuses.contains "UNREACHED" then s!", {count "UNREACHED"} unreached" else "")
      else ""
    -- A universal claim names every case that fails; an existence claim fails in all of them.
    let failing := if status == "FAIL" && rs.head!.ob.expect == "Valid" then
      (rs.filter fun x => x.status == "FAIL" && !x.ob.caseLabel.isEmpty).map (·.ob.caseLabel) else []
    folded := folded.push { r := chosen, id := gid, status, cases, failing,
                            stopped := (rs.filter (·.verdict == "time limit")).map (·.ob.module) }
  return folded

/-! ## The command line -/

structure Args where
  blueprint : String := ""
  formal : String := "."
  config : String := "universal.json"
  nixShell : String := ""
  noRun : Bool := false
  cfg : Config := {}
  jobs : Nat := 4
  validators : Array String := #[]

def usage : String := "\n".intercalate [
  "usage: lake exe universal --blueprint PLUTUS_JSON [options] VALIDATOR...",
  "  --formal DIR       the formal/ directory (default .)",
  "  --config FILE      waivers and switches (default universal.json)",
  "  --nix-shell FLAKE  run lake inside `nix develop FLAKE` (default $UNIVERSAL_NIX_SHELL)",
  "  --no-run           generate the modules only",
  "  --quick            pin every sum type to its first constructor: faster, weaker",
  "  --no-validity      drop the ledger-validity hypothesis",
  "  --prep             apply the script once with #prep_uplc (fast on small scripts, blows up on vesting)",
  "  --prep-steps N     CEK step bound for #prep_uplc (default 60000)",
  "  --timeout N        seconds per module, wall clock; a slower module is stopped and reports UNDETERMINED (default 600)",
  "  --max-cases N      modules per check in full mode; sums that do not fit stay open inside each module (default 16)",
  "  --jobs N           modules built in parallel; each runs Lean and Z3, so keep it below the core count (default 4)"]

partial def parseArgs (args : List String) (a : Args) : Except String Args :=
  let nat := fun (flag v : String) => match v.toNat? with
    | some n => Except.ok n
    | none => Except.error s!"{flag} takes a number, not {v}"
  match args with
  | [] => if a.blueprint.isEmpty then .error "--blueprint is required"
          else if a.validators.isEmpty then .error "name at least one validator" else .ok a
  | "--blueprint" :: v :: rest => parseArgs rest { a with blueprint := v }
  | "--formal" :: v :: rest => parseArgs rest { a with formal := v }
  | "--config" :: v :: rest => parseArgs rest { a with config := v }
  | "--nix-shell" :: v :: rest => parseArgs rest { a with nixShell := v }
  | "--no-run" :: rest => parseArgs rest { a with noRun := true }
  | "--quick" :: rest => parseArgs rest { a with cfg.quick := true }
  | "--no-validity" :: rest => parseArgs rest { a with cfg.noValidity := true }
  | "--prep" :: rest => parseArgs rest { a with cfg.noPrep := false }
  | "--prep-steps" :: v :: rest => do parseArgs rest { a with cfg.prepSteps := ← nat "--prep-steps" v }
  | "--timeout" :: v :: rest => do parseArgs rest { a with cfg.timeout := ← nat "--timeout" v }
  | "--max-cases" :: v :: rest => do parseArgs rest { a with cfg.maxCases := ← nat "--max-cases" v }
  | "--jobs" :: v :: rest => do parseArgs rest { a with jobs := ← nat "--jobs" v }
  | flag :: rest =>
    if flag.startsWith "--" then .error s!"unknown option {flag}"
    else parseArgs rest { a with validators := a.validators.push flag }

def padRight (s : String) (n : Nat) : String := s.pushn ' ' (n - s.length)

def pyList (xs : List String) : String := "[" ++ ", ".intercalate (xs.map fun x => s!"'{x}'") ++ "]"

def run (a : Args) : IO UInt32 := do
  let cfg := a.cfg
  let formal ← IO.FS.realPath a.formal
  let bp ← IO.ofExcept (Json.parse (← IO.FS.readFile a.blueprint))
  let defs := (field? bp "definitions").getD (Json.mkObj [])
  let cfgPath := formal / a.config
  let waivers ← if ← cfgPath.pathExists then IO.ofExcept (Json.parse (← IO.FS.readFile cfgPath)) else pure (Json.mkObj [])
  let today := toString (← Std.Time.PlainDate.now)
  let mut worst : UInt32 := 0

  -- Every name is checked before anything runs; a usage error is a run with no verdict (exit 2).
  let validators := (arr? bp "validators").getD #[]
  let mut spends : Array (String × Json × List String) := #[]
  for name in a.validators do
    let entries := validators.filter fun v => (orElse (str? v "title") "").startsWith s!"{name}.{name}."
    let spend := entries.find? fun v => (orElse (str? v "title") "").endsWith ".spend"
    if entries.isEmpty then
      IO.eprintln s!"no blueprint entry for {name}"
      return 2
    match spend with
    | some s =>
      if (field? s "parameters").isSome then
        IO.eprintln s!"{name}: the prototype covers unparameterised validators with a spend handler"
        return 2
      let handlers := entries.toList.map fun v => ((orElse (str? v "title") "").splitOn ".").getLast!
      spends := spends.push (name, s, handlers.filter (· != "else"))
    | none =>
      IO.eprintln s!"{name}: the prototype covers unparameterised validators with a spend handler"
      return 2

  for (name, spend, declared) in spends do
    let schemaOf := fun (k : String) => (field? spend k).bind (field? · "schema")
    -- The input datum, then the continuing output's datum with its own leaves and its own choices,
    -- so every spend check sees an output whose datum differs from the input's in any way the
    -- shape allows, then the redeemer.
    let built : Except String _ := do
      let (datumTerm, s1) ← (match schemaOf "datum" with
        | some sc => gen defs cfg.quick sc "d"
        | none => pure "Data.I 0").run { pfx := "d_" }
      let (outTerm, s2) ← (match schemaOf "datum" with
        | some sc => gen defs cfg.quick sc "d"
        | none => pure "Data.I 0").run { pfx := "o_", label := "output ", n := s1.n }
      let (vars, s3) ← (match schemaOf "redeemer" with
        | some sc => variants defs cfg.quick sc "r"
        | none => pure #[("", "Data.I 0", 0, #[])]).run { pfx := "r_", label := "redeemer ", n := s2.n }
      return (datumTerm, outTerm, vars, s1.binders ++ s2.binders ++ s3.binders, s1.choices, s2.choices)
    let (datumTerm, outTerm, vars, leaves, inChoices, outChoices) ← IO.ofExcept built
    let hex := orElse (str? spend "compiledCode") ""
    let g := generate cfg name hex declared datumTerm outTerm vars leaves inChoices.toList outChoices.toList
    let d := formal / "Universal" / "Demo" / g.mod
    IO.FS.createDirAll d
    for entry in ← d.readDir do
      if entry.path.extension == some "lean" then IO.FS.removeFile entry.path
    IO.FS.writeFile (d / "Base.lean") g.base
    for (mname, src) in g.modules do
      IO.FS.writeFile (d / s!"{(mname.splitOn ".").getLast!}.lean") src
    let mode := if cfg.quick then "quick" else "full"
    let aggregator := [s!"-- Generated by `lake exe universal`: every check for `{name}`. Do not edit; regenerate.",
      s!"-- `lake build Universal.Demo.{g.mod}` builds them all ({mode} mode)."] ++ (g.modules.toList.map fun (m, _) => s!"import {m}")
    IO.FS.writeFile (formal / "Universal" / "Demo" / s!"{g.mod}.lean") ("\n".intercalate aggregator ++ "\n")
    let nChecks := (g.obligations.foldl (fun gs o => if gs.contains o.group then gs else gs.push o.group) #[]).size
    let modeNote := if cfg.quick then "quick mode: sum types pinned to the first constructor" else "full mode"
    IO.println s!"\n== {name}: declared handlers {pyList declared}; {nChecks} checks in {g.obligations.size} modules -> Universal/Demo/{g.mod}/ ({modeNote})"
    if a.noRun then continue
    IO.println ("   PASS holds within the generated shape (see Universal/Notes.lean). HOLE = wrong in almost every contract." ++
      " REVIEW = can be by design: confirm or waive with a reason. UNREACHED = no accepted spend for this action," ++
      " so the check proved nothing. UNDETERMINED = stopped by the time limit. UNKNOWN = Blaster gave no verdict.")
    let (report?, raw) ← runAndParse formal cfg s!"Universal.Demo.{g.mod}.Base" g.obligations a.nixShell a.jobs
    IO.FS.writeFile (d / "build.log") raw
    if report?.isNone then
      IO.println s!"Universal.Demo.{g.mod}.Base does not build, so no check ran; see Universal/Demo/{g.mod}/build.log"
      worst := max worst 2
      continue
    let report := report?.getD #[]
    let entries := (field? waivers name).getD (Json.mkObj [])
    for r in foldCases report do
      let w := (field? entries r.id).getD (Json.mkObj [])
      let present := w != Json.mkObj []
      let state := orElse (str? w "state") (if present then "waived" else "")
      let expired := state == "waived" && (orElse (str? w "until") "9999") < today
      let mut status := r.status
      if state == "off" || (!r.r.ob.defaultOn && state != "on") then status := "OFF"
      else if state == "waived" && !expired && status == "FAIL" then status := "WAIVED"
      else if status == "FAIL" && r.r.ob.severity == "review" then status := "REVIEW"
      let label := if status == "FAIL" then "HOLE" else status
      let cases := if r.cases.isEmpty then "" else s!" ({r.cases})"
      IO.println s!"{padRight label 12} {padRight r.id 16} {r.r.ob.title}{cases}"
      if status == "FAIL" || status == "REVIEW" then
        IO.println s!"             consequence: {r.r.ob.consequence}"
        for c in r.failing do
          IO.println s!"             fails when: {c}"
      if status == "FAIL" || status == "REVIEW" || (status == "PASS" && r.r.ob.expect == "Falsified") then
        if !r.r.witness.isEmpty then
          let which := if status == "PASS" then "witness"
            else "counterexample" ++ (if r.failing.length > 1 then " for the first case" else "")
          IO.println s!"             {which}: {r.r.witness}"
      if status == "WAIVED" then
        let who := (str? w "owner").map (s!" by {·}") |>.getD ""
        let expiry := (str? w "until").map (s!" until {·}") |>.getD ""
        IO.println s!"             waived{who}{expiry}, all cases: {orElse (str? w "reason") ""}"
      if expired && r.status == "FAIL" then
        IO.println s!"             the waiver expired on {orElse (str? w "until") ""}, so it no longer applies"
      if status == "OFF" then
        let how := if state == "off" then "switched off in universal.json"
          else "off by default; enable it with {\"state\": \"on\"} in universal.json"
        IO.println s!"             {how} (result would be {r.status})"
      if !r.stopped.isEmpty then
        let names := ", ".intercalate (r.stopped.map fun m => (m.splitOn ".").getLast!)
        IO.println s!"             stopped after {cfg.timeout} s: {names}"
      if status == "UNKNOWN" then
        IO.println s!"             blaster said: {r.r.verdict}; see Universal/Demo/{g.mod}/build.log"
      if status == "FAIL" then worst := max worst 1
      if status == "UNDETERMINED" || status == "UNREACHED" || status == "UNKNOWN" then worst := max worst 2
  return worst

end GenUniversal

def main (args : List String) : IO UInt32 := do
  let nixShell := (← IO.getEnv "UNIVERSAL_NIX_SHELL").getD ""
  match GenUniversal.parseArgs args { nixShell } with
  | .ok a => GenUniversal.run a
  | .error e =>
    IO.eprintln s!"{e}\n{GenUniversal.usage}"
    return 2
