import Lean.Data.Json

namespace Workflow.Tests.Support

open Lean

def check (label : String) (condition : Bool) : IO Unit := do
  unless condition do throw (IO.userError s!"FAIL: {label}")

def stringField (value : Json) (key : String) : IO String :=
  IO.ofExcept do (← value.getObjVal? key).getStr?

def rows (report : Json) : IO (Array Json) :=
  IO.ofExcept do (← report.getObjVal? "checks").getArr?

structure CLIRun where
  exitCode : UInt32
  report : Json
  directory : System.FilePath
  input : String

def invoke (blueprint selector : String) (checkId : Option String) (budgetMs : Nat) : IO CLIRun := do
  let original ← IO.FS.readFile blueprint
  let selection := checkId.map (fun id => #["--check", id]) |>.getD #[]
  let output ← IO.Process.output {
    cmd := "lake"
    args := #["exe", "universal", blueprint, selector] ++ selection ++
      #["--timeout-ms", toString budgetMs] }
  let some reportLine := (output.stdout.splitOn "\n").find? (·.startsWith "Report: ")
    | throw (IO.userError s!"CLI did not save a report:\n{output.stdout}{output.stderr}")
  let reportPath := System.FilePath.mk ((reportLine.drop 8).trim)
  let report ← IO.ofExcept (Json.parse (← IO.FS.readFile reportPath))
  let some directory := reportPath.parent | throw (IO.userError "missing report directory")
  check "CLI preserves the supplied input" ((← IO.FS.readFile blueprint) == original)
  let root ← IO.FS.realPath "output"
  check "CLI uses the local output folder" (directory.parent == some root)
  check "plain report exists" (← (directory / "report.txt").pathExists)
  check "report points to its actual output directory"
    ((← stringField report "evidenceDirectory") == directory.toString)
  IO.print output.stdout
  return { exitCode := output.exitCode, report, directory, input := original }

def expectOutcome (label : String) (run : CLIRun) (status : String) (exitCode : UInt32) : IO Unit := do
  let savedExit ← IO.ofExcept do (← run.report.getObjVal? "exitCode").getNat?
  check s!"{label}: process exit code" (run.exitCode == exitCode)
  check s!"{label}: report exit code" (savedExit == exitCode.toNat)
  check s!"{label}: report status" ((← stringField run.report "status") == status)

def expectRows (label : String) (run : CLIRun) (count : Nat)
    (property status observed bound : String) : IO Unit := do
  let checks ← rows run.report
  check s!"{label}: requested obligation count" (checks.size == count)
  for row in checks do
    check s!"{label}: property identity" ((← stringField row "property") == property)
    check s!"{label}: row status" ((← stringField row "status") == status)
    check s!"{label}: raw observation" ((← stringField row "observed") == observed)
    check s!"{label}: stated bound" (((← stringField row "scope").splitOn bound).length > 1)

def expectProblem (label : String) (run : CLIRun) (fragment : String) : IO Unit := do
  let problems ← IO.ofExcept do (← run.report.getObjVal? "problems").getArr?
  check label (problems.any fun item =>
    (((item.getStr?).toOption.getD "").splitOn fragment).length > 1)

def expectArtifacts (label : String) (run : CLIRun) (sources : Array String) : IO Unit := do
  check s!"{label}: exact input snapshot" ((← IO.FS.readFile (run.directory / "input.json")) == run.input)
  for source in sources do
    check s!"{label}: retained {source}" (← (run.directory / "Generated/Workflow" / source).pathExists)
  let manifest ← IO.ofExcept (Json.parse (← IO.FS.readFile (run.directory / "execution.json")))
  let modules ← IO.ofExcept do (← manifest.getObjVal? "modules").getArr?
  for item in modules do
    let path := System.FilePath.mk (← stringField item "path")
    check s!"{label}: recorded module location" (path.parent == some (run.directory / "Generated/Workflow"))
    check s!"{label}: recorded module exists" (← path.pathExists)
    check s!"{label}: compiler stdout retained" (← (path.withExtension "stdout.log").pathExists)
    check s!"{label}: compiler stderr retained" (← (path.withExtension "stderr.log").pathExists)

end Workflow.Tests.Support
