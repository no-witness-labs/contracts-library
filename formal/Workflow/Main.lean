import Workflow
import Formal.Universal.Properties

namespace Workflow.Main

private def usage : String :=
  "usage: lake exe universal BLUEPRINT VALIDATOR [--check PROPERTY_ID] [--timeout-ms MILLISECONDS]"

private structure Request where
  path : System.FilePath
  selector : String
  checkId : Option String := none
  budgetMs : Nat := 30000

private def parseOptions : List String → Request → Except String Request
  | [], request => .ok request
  | "--check" :: id :: rest, request => parseOptions rest { request with checkId := some id }
  | "--timeout-ms" :: value :: rest, request => do
    let some budget := value.toNat? | throw "timeout must be positive milliseconds"
    if budget == 0 then throw "timeout must be positive milliseconds"
    parseOptions rest { request with budgetMs := budget }
  | _, _ => .error usage

private def finish (report : Reporter.Report) (source : Option String := none) : IO UInt32 := do
  try
    let directory ← match report.evidenceDirectory with
      | some value => pure value
      | none => IO.FS.createTempDir
    if let some original := source then IO.FS.writeFile (directory / "input.json") original
    report.write directory
    IO.print report.text
    IO.println s!"Report: {directory / "report.json"}"
    return report.exitCode
  catch error =>
    IO.eprintln s!"INCONCLUSIVE: could not save the report: {error}"
    return 2

private def runRequest (request : Request) : IO UInt32 := do
  let input ← match ← Input.read request.path request.selector with
    | .ok value => pure value
    | .error error => return ← finish (Reporter.failure request.selector (toString error))
  let provider ← match Generator.selectProvider request.checkId with
    | .ok value => pure value
    | .error message => return ← finish (Reporter.failure input.target.name message) (some input.sourceText)
  let plan ← match Generator.generate provider input.target "Generated.Workflow" with
    | .ok value => pure value
    | .error error => return ← finish (Reporter.failure input.target.name (toString error)) (some input.sourceText)
  let leanPath := (← IO.getEnv "LEAN_PATH").getD ""
  let result ← match ← Executor.run plan { leanPath, budgetMs := request.budgetMs } with
    | .ok value => pure value
    | .error message => return ← finish (Reporter.failure input.target.name message) (some input.sourceText)
  finish (Reporter.build plan result) (some input.sourceText)

def run (args : List String) : IO UInt32 := do
  match args with
  | ["--help"] => IO.println usage; return 0
  | path :: selector :: rest =>
    match parseOptions rest { path, selector } with
    | .error message => finish (Reporter.failure selector message)
    | .ok request => runRequest request
  | _ => finish (Reporter.failure "unselected" usage)

end Workflow.Main

def main (args : List String) : IO UInt32 := Workflow.Main.run args
