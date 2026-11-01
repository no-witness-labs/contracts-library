import Workflow.Assessor

namespace Workflow.App

open Lean

/-- Encode a logical name as one filesystem component without losing identity. -/
def safeName (name : String) : String :=
  String.join (name.toUTF8.toList.map fun byte =>
    let value := byte.toNat
    let ordinary := (value >= 48 && value <= 57) || (value >= 65 && value <= 90) ||
      (value >= 97 && value <= 122) || value == 45 || value == 95 ||
      (value == 46 && name != "." && name != "..")
    if ordinary then (Char.ofNat value).toString
    else
      let hex := "0123456789ABCDEF".toList.toArray
      "%" ++ (hex[value / 16]!).toString ++ (hex[value % 16]!).toString)

def checkFolder (id : CheckId) : String :=
  s!"{safeName id.propertyId}-v{id.definitionVersion}-{safeName id.modelId}"

def checkDirectory (name : String) (id : CheckId) : System.FilePath :=
  System.FilePath.mk "validators" / safeName name / checkFolder id

structure CheckRun where
  id : CheckId
  resultFile : Option System.FilePath := none
  error : Option String := none
  result : Option Assessor.CheckResult := none
  deriving Inhabited

structure ValidatorRun where
  name : String
  preparationError : Option String := none
  checks : Array CheckRun := #[]
  deriving Inhabited

structure RunRecord where
  directory : System.FilePath
  input : Option System.FilePath := none
  sourceIndex : Option System.FilePath := none
  options : Json := .null
  validators : Array ValidatorRun := #[]
  finished : Bool := false
  errors : Array String := #[]
  elapsedMs : Nat := 0

def CheckRun.toJson (check : CheckRun) : Json := Json.mkObj [
  ("property", Json.mkObj [("id", .str check.id.propertyId),
    ("definition_version", Lean.toJson check.id.definitionVersion)]),
  ("tx_model", .str check.id.modelId),
  ("result", check.resultFile.map (fun path => Json.str path.toString) |>.getD .null),
  ("error", check.error.map Json.str |>.getD .null)]

def ValidatorRun.toJson (validator : ValidatorRun) : Json := Json.mkObj [
  ("name", .str validator.name),
  ("preparation_error", validator.preparationError.map Json.str |>.getD .null),
  ("checks", .arr (validator.checks.map CheckRun.toJson))]

def RunRecord.toJson (run : RunRecord) : Json := Json.mkObj [
  ("input", run.input.map (fun path => Json.str path.toString) |>.getD .null),
  ("source_index", run.sourceIndex.map (fun path => Json.str path.toString) |>.getD .null),
  ("options", run.options), ("validators", .arr (run.validators.map ValidatorRun.toJson)),
  ("finished", .bool run.finished), ("errors", Lean.toJson run.errors),
  ("elapsed_ms", Lean.toJson run.elapsedMs)]

def writeText (path : System.FilePath) (contents : String) : IO Unit := do
  let handle ← IO.FS.Handle.mk path .write
  handle.putStr contents
  handle.flush

def RunRecord.save (run : RunRecord) : IO Unit := do
  let temporary := run.directory / "run.json.tmp"
  writeText temporary (run.toJson.pretty ++ "\n")
  IO.FS.rename temporary (run.directory / "run.json")

/-- Exit codes describe app completion and retention; check verdicts remain data. -/
def RunRecord.exitCode (run : RunRecord) : UInt32 :=
  if !run.finished || !run.errors.isEmpty || run.validators.any (fun validator =>
      validator.preparationError.isSome || validator.checks.any (·.error.isSome)) then 2 else 0

private def terminalText (text : String) : String :=
  String.join (text.toList.map fun character =>
    if character == '\n' then "\\n"
    else if character == '\r' then "\\r"
    else if character == '\t' then "\\t"
    else if character.toNat < 32 || character.toNat == 127 then
      "<" ++ toString character.toNat ++ ">"
    else character.toString)

private def padRight (text : String) (width : Nat) : String :=
  text ++ String.mk (List.replicate (width - text.length) ' ')

private def padLeft (text : String) (width : Nat) : String :=
  String.mk (List.replicate (width - text.length) ' ') ++ text

def RunRecord.text (run : RunRecord) : String := Id.run do
  let labels := run.validators.map fun validator =>
    let label := terminalText validator.name
    if label.length > 56 then label.take 53 ++ "..." else label
  let width := labels.foldl (fun width name => max width name.length) 9
  let mut lines := #["Plutus UPV", "",
    s!"{padRight "Validator" width}  {padLeft "PASS" 5}  {padLeft "FAIL" 5}  {padLeft "INCONCLUSIVE" 12}",
    String.mk (List.replicate (width + 28) '-')]
  let mut total := 0
  let mut recorded := 0
  for index in [:run.validators.size] do
    let validator := run.validators[index]!
    let count := fun status => (validator.checks.filter fun check =>
      check.result.any (·.status == status)).size
    lines := lines.push s!"{padRight labels[index]! width}  {padLeft (toString (count .pass)) 5}  {padLeft (toString (count .fail)) 5}  {padLeft (toString (count .inconclusive)) 12}"
    total := total + validator.checks.size
    recorded := recorded + (validator.checks.filter (·.resultFile.isSome)).size
  lines := lines ++ #["", s!"Recorded checks: {recorded}/{total}", s!"Elapsed: {run.elapsedMs} ms"]
  if total == 0 && run.errors.isEmpty then
    lines := lines.push "No checks selected; verification was not run."
  for validator in run.validators do
    if let some message := validator.preparationError then
      lines := lines.push s!"Preparation error ({terminalText validator.name}): {terminalText message}"
    for check in validator.checks do
      if let some message := check.error then
        lines := lines.push s!"Error ({terminalText validator.name}, {terminalText check.id.propertyId}, {terminalText check.id.modelId}): {terminalText message}"
  for message in run.errors do lines := lines.push s!"Error: {terminalText message}"
  if !run.finished then lines := lines.push "Run did not finish; inspect the saved index and files."
  lines := lines ++ #[s!"Output: {run.directory}", s!"Review: {run.directory / "README.md"}",
    s!"Index: {run.directory / "run.json"}"]
  return String.intercalate "\n" lines.toList ++ "\n"

end Workflow.App
