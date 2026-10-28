import Workflow.Input
import Workflow.Generator
import Workflow.Executor
import Formal.Universal.Properties

open Workflow

namespace Workflow.Executor.Integration

private def execute (plan : GenerationPlan) (leanPath : String) (budget : Nat) : IO Executor.Result := do
  match ← Executor.run plan { leanPath, budgetMs := budget } with
  | .ok result => return result
  | .error message => throw (IO.userError message)

def run (args : List String) : IO Unit := do
  let environment ← IO.Process.output { cmd := "lake", args := #["env", "printenv", "LEAN_PATH"] }
  unless environment.exitCode == 0 do throw (IO.userError environment.stderr)
  let leanPath := environment.stdout.trim
  let source ← IO.FS.readFile "Workflow/Executor/Fixtures/outcomes.lean.txt"
  let controls : GenerationPlan := {
    targetName := "executor-controls", modules := #[⟨"Controls.Outcomes", source⟩]
    jobs := #[
      { propertyId := "fixture-valid", name := "good", moduleName := "Controls.Outcomes",
        statement := "∀ x : Int, x = x", expected := .valid, scope := "fixture only" },
      { propertyId := "fixture-falsified", name := "bad", moduleName := "Controls.Outcomes",
        statement := "(1 : Int) = 2", expected := .falsified, scope := "fixture only" }] }
  let controlResult ← execute controls leanPath 15000
  unless controlResult.state == .completed && controlResult.jobs.size == 2 &&
      controlResult.jobs.any (fun item => item.job.name == "good" && item.observed == .valid) &&
      controlResult.jobs.any (fun item => item.job.name == "bad" && item.observed == .falsified) do
    throw (IO.userError s!"real solver controls failed; evidence: {reprStr (controlResult.directory.map (·.toString))}")
  IO.println s!"Real solver controls observed Valid and Falsified; evidence: {(controlResult.directory.map (·.toString)).getD "none"}"
  match args with
  | [] => pure ()
  | [path, selector, budgetText] =>
    let some budget := budgetText.toNat? | throw (IO.userError "budget must be positive milliseconds")
    let input ← match ← Input.read path selector with
      | .ok value => pure value
      | .error error => throw (IO.userError (toString error))
    let plan ← match Generator.generate Generator.OtherPurpose.provider input.target "Executed.Validator" with
      | .ok value => pure value
      | .error error => throw (IO.userError (toString error))
    let result ← execute plan leanPath budget
    if let some directory := result.directory then
      IO.FS.writeFile (directory / "input.json") input.sourceText
    IO.println s!"{input.target.name}: {reprStr result.state}; {result.elapsedMs} ms; evidence: {(result.directory.map (·.toString)).getD "none"}"
    IO.println s!"Observed: {(result.jobs.filter (·.observed == .valid)).size} Valid, {(result.jobs.filter (·.observed == .falsified)).size} Falsified, {(result.jobs.filter (·.observed == .inconclusive)).size} inconclusive"
    if result.state == .error then throw (IO.userError (String.intercalate "\n" result.problems.toList))
  | _ => throw (IO.userError "usage: workflow_executor_integration [BLUEPRINT VALIDATOR BUDGET_MS]")

end Workflow.Executor.Integration

def main (args : List String) : IO Unit := Workflow.Executor.Integration.run args
