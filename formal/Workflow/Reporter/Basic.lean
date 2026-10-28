import Workflow.Executor.Types

namespace Workflow.Reporter

open Lean

inductive Status where
  | pass | fail | inconclusive
  deriving BEq, Repr

def Status.label : Status → String
  | .pass => "PASS"
  | .fail => "FAIL"
  | .inconclusive => "INCONCLUSIVE"

structure Row where
  job : CheckJob
  observed : Option Executor.ObservedResult
  status : Status
  issues : Array String

structure Report where
  target : String
  status : Status
  rows : Array Row := #[]
  problems : Array String := #[]
  notes : Array String := #[]
  evidenceDirectory : Option System.FilePath := none

def Report.exitCode (report : Report) : UInt32 :=
  match report.status with
  | .pass => 0
  | .fail => 1
  | .inconclusive => 2

private def sameIdentity (left right : CheckJob) : Bool :=
  left.name == right.name && left.moduleName == right.moduleName

private def sameMetadata (left right : CheckJob) : Bool :=
  sameIdentity left right && left.propertyId == right.propertyId &&
    left.expected == right.expected && left.statement == right.statement && left.scope == right.scope

/-- Compare only declared expectations; property IDs and backend messages need no special cases. -/
def build (plan : GenerationPlan) (execution : Executor.Result) : Report := Id.run do
  let mut problems := execution.problems
  unless execution.state == .completed do
    problems := problems.push s!"execution did not complete: {reprStr execution.state}"
  if plan.jobs.isEmpty then problems := problems.push "no obligations were executed"
  if plan.jobs.isEmpty != (plan.status == .noObligations) then
    problems := problems.push "generation status and job count disagree"
  if execution.jobs.any (fun result => !plan.jobs.any (sameIdentity result.job)) then
    problems := problems.push "execution contains observations for unrequested jobs"
  let incomplete := !problems.isEmpty
  let mut rows := #[]
  for job in plan.jobs do
    let found := execution.jobs.filter (fun result => sameIdentity result.job job)
    let mut issues : Array String := #[]
    let mut observed := none
    if (plan.jobs.filter (sameIdentity job)).size != 1 then
      issues := issues.push "duplicate requested job"
    match found.toList with
    | [result] =>
      observed := some result.observed
      issues := issues ++ result.issues
      unless sameMetadata job result.job do issues := issues.push "job metadata changed during execution"
    | [] => issues := issues.push "missing job observation"
    | _ => issues := issues.push "duplicate job observations"
    let status := if incomplete || !issues.isEmpty then Status.inconclusive else
      match observed with
      | some .valid => if job.expected == .valid then .pass else .fail
      | some .falsified => if job.expected == .falsified then .pass else .fail
      | _ => .inconclusive
    rows := rows.push { job, observed, status, issues }
  let status := if incomplete || rows.any (·.status == .inconclusive) then Status.inconclusive
    else if rows.any (·.status == .fail) then .fail else .pass
  return { target := plan.targetName, status, rows, problems, notes := plan.notes
           evidenceDirectory := execution.directory }

def failure (target message : String) : Report :=
  { target, status := .inconclusive, problems := #[message] }

private def expectedText : ExpectedResult → String
  | .valid => "valid"
  | .falsified => "falsified"

private def observedText : Executor.ObservedResult → String
  | .valid => "valid"
  | .falsified => "falsified"
  | .inconclusive => "inconclusive"

def Report.toJson (report : Report) : Json :=
  let rows := report.rows.map fun row => Json.mkObj [
    ("property", .str row.job.propertyId), ("name", .str row.job.name),
    ("module", .str row.job.moduleName), ("scope", .str row.job.scope),
    ("expected", .str (expectedText row.job.expected)),
    ("observed", row.observed.map (fun value => Json.str (observedText value)) |>.getD .null),
    ("status", .str row.status.label), ("issues", Lean.toJson row.issues)]
  Json.mkObj [
    ("schemaVersion", Lean.toJson (1 : Nat)), ("target", .str report.target),
    ("status", .str report.status.label), ("exitCode", Lean.toJson report.exitCode.toNat),
    ("checks", .arr rows), ("problems", Lean.toJson report.problems), ("notes", Lean.toJson report.notes),
    ("evidenceDirectory", report.evidenceDirectory.map (fun path => Json.str path.toString) |>.getD .null)]

private def oneLine (text : String) : String :=
  text.replace "\r" "\\r" |>.replace "\n" "\\n" |>.replace "\t" "\\t"

def Report.text (report : Report) : String := Id.run do
  let mut lines := #[s!"Target: {oneLine report.target}"]
  for row in report.rows do
    lines := lines.push s!"{row.status.label} {oneLine row.job.propertyId} {oneLine row.job.name}"
  let count := fun status => (report.rows.filter (·.status == status)).size
  lines := lines.push s!"Summary: {count .pass} PASS, {count .fail} FAIL, {count .inconclusive} INCONCLUSIVE"
  lines := lines.push s!"Overall: {report.status.label} (exit {report.exitCode})"
  if let some problem := report.problems[0]? then
    lines := lines.push s!"Reason: {oneLine problem}"
  if let some directory := report.evidenceDirectory then
    lines := lines.push s!"Evidence: {oneLine directory.toString}"
  return String.intercalate "\n" lines.toList ++ "\n"

/-- Persist only the simple summary; raw diagnostics remain in Executor's evidence. -/
def Report.write (report : Report) (directory : System.FilePath) : IO Unit := do
  IO.FS.createDirAll directory
  IO.FS.writeFile (directory / "report.json") (report.toJson.pretty ++ "\n")
  IO.FS.writeFile (directory / "report.txt") report.text

end Workflow.Reporter
