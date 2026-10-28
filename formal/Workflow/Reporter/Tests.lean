import Workflow.Reporter

open Lean Workflow

namespace Workflow.Reporter.Tests

private def check (label : String) (condition : Bool) : IO Unit := do
  unless condition do throw (IO.userError s!"FAIL: {label}")

private def job (name := "proof") (expected := ExpectedResult.valid) : CheckJob :=
  { propertyId := "fixture", name, moduleName := "Fixture.Checks", statement := "True",
    expected, scope := "fixture scope" }

private def plan (jobs : Array CheckJob) : GenerationPlan :=
  { targetName := "fixture.target", modules := #[], jobs,
    status := if jobs.isEmpty then .noObligations else .ready }

private def observation (metadata : CheckJob) (observed : Executor.ObservedResult) : Executor.JobObservation :=
  { job := metadata, observed }

private def completed (jobs : Array Executor.JobObservation) : Executor.Result :=
  { state := .completed, jobs }

private def one (report : Report) : IO Row :=
  match report.rows[0]? with
  | some row => pure row
  | none => throw (IO.userError "missing report row")

def run : IO Unit := do
  let good := build (plan #[job]) (completed #[observation job .valid])
  check "matching result passes" (good.status == .pass && good.exitCode == 0)
  let bad := build (plan #[job]) (completed #[observation job .falsified])
  check "unexpected counterexample fails" (bad.status == .fail && bad.exitCode == 1)
  let witness := job "witness" .falsified
  let found := build (plan #[witness]) (completed #[observation witness .falsified])
  check "expected counterexample can pass" (found.status == .pass && found.exitCode == 0)
  let missingWitness := build (plan #[witness]) (completed #[observation witness .valid])
  check "unexpected valid result fails a witness job" (missingWitness.exitCode == 1)
  let unknown := build (plan #[job]) (completed #[observation job .inconclusive])
  check "unknown does not pass" (unknown.status == .inconclusive && unknown.exitCode == 2)

  for state in [Executor.RunState.timedOut, .error, .noObligations] do
    let report := build (plan #[job]) { completed #[observation job .valid] with state }
    let row ← one report
    check "incomplete run overrides a positive row"
      (report.exitCode == 2 && row.status == .inconclusive && row.observed == some .valid)
  let errored := build (plan #[job])
    { completed #[observation job .valid] with problems := #["compiler problem"] }
  check "run problem overrides positive evidence" (errored.exitCode == 2)
  let rowIssue := build (plan #[job])
    (completed #[{ observation job .valid with issues := #["conflicting evidence"] }])
  check "job problem overrides positive evidence" (rowIssue.exitCode == 2)
  let absent := build (plan #[job]) (completed #[])
  check "missing observation is inconclusive" (absent.exitCode == 2)
  let duplicate := build (plan #[job]) (completed #[observation job .valid, observation job .valid])
  check "duplicate observation is inconclusive" (duplicate.exitCode == 2)
  let duplicatePlan := build (plan #[job, job]) (completed #[observation job .valid])
  check "duplicate requested job is inconclusive" (duplicatePlan.exitCode == 2)
  let extra := build (plan #[job])
    (completed #[observation job .valid, observation (job "unrequested") .valid])
  check "unrequested observation is inconclusive" (extra.exitCode == 2)
  let changed := build (plan #[job]) (completed #[observation { job with expected := .falsified } .valid])
  check "changed expectation is inconclusive" (changed.exitCode == 2)
  let changedScope := build (plan #[job]) (completed #[observation { job with scope := "different" } .valid])
  check "changed scope is inconclusive" (changedScope.exitCode == 2)
  let empty := build (plan #[]) { state := .noObligations }
  check "empty plan is not a pass" (empty.status == .inconclusive && empty.exitCode == 2)
  let mixed := build (plan #[job, witness])
    (completed #[observation job .falsified, observation witness .inconclusive])
  check "inconclusive takes precedence over failure" (mixed.exitCode == 2)

  let some row := good.toJson.getObjVal? "checks" |>.toOption.bind (·.getArr?.toOption)
    | throw (IO.userError "missing JSON checks")
  let some first := row[0]? | throw (IO.userError "missing JSON check row")
  check "JSON keeps expectation" ((first.getObjVal? "expected").toOption == some (.str "valid"))
  check "JSON keeps observed result" ((first.getObjVal? "observed").toOption == some (.str "valid"))
  check "JSON keeps scope" ((first.getObjVal? "scope").toOption == some (.str "fixture scope"))
  check "plain text contains result and summary"
    ((good.text.splitOn "PASS fixture proof").length == 2 &&
      (good.text.splitOn "Overall: PASS (exit 0)").length == 2)
  check "plain summary matches fixture"
    (good.text == (← IO.FS.readFile "Workflow/Reporter/Fixtures/summary.txt"))
  let escaped := failure "target\nname" "problem\ntext"
  check "plain text escapes line breaks" ((escaped.text.splitOn "Target: target\\nname").length == 2)
  IO.FS.withTempDir fun directory => do
    good.write directory
    check "text report written" ((← IO.FS.readFile (directory / "report.txt")) == good.text)
    let saved ← IO.FS.readFile (directory / "report.json")
    check "JSON report written" ((Json.parse saved).toOption == some good.toJson)
  IO.println "Reporter fixture checks passed."

end Workflow.Reporter.Tests

def main : IO Unit := Workflow.Reporter.Tests.run
