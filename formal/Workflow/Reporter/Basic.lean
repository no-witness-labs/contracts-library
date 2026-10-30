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
  evidenceComplete : Bool := false

structure Report where
  target : String
  status : Status
  rows : Array Row := #[]
  problems : Array String := #[]
  notes : Array String := #[]
  evidenceDirectory : Option System.FilePath := none
  propertyDefinition : Option PropertyDefinition := none

def Report.exitCode (report : Report) : UInt32 :=
  match report.status with
  | .pass => 0
  | .fail => 1
  | .inconclusive => 2

private def sameIdentity (left right : CheckJob) : Bool :=
  left.name == right.name && left.moduleName == right.moduleName

private def sameMetadata (left right : CheckJob) : Bool :=
  sameIdentity left right && left.propertyId == right.propertyId &&
    left.expected == right.expected && left.statement == right.statement && left.scope == right.scope &&
    left.role == right.role && left.applicability == right.applicability &&
    left.txModelId == right.txModelId && left.binding == right.binding

private def matchesRef (reference : JobRef) (job : CheckJob) : Bool :=
  reference.moduleName == job.moduleName && reference.name == job.name

private structure CheckedObservation where
  row : Row
  trustworthy : Bool

private def observe (execution : Executor.Result)
    (integrityBroken : Bool) (job : CheckJob) : CheckedObservation := Id.run do
  let found := execution.jobs.filter (fun result => sameIdentity result.job job)
  let mut issues : Array String := #[]
  let mut observed := none
  let mut evidenceComplete := false
  if integrityBroken then issues := issues.push "run attribution or generation plan is inconsistent"
  match found.toList with
  | [result] =>
    observed := some result.observed
    evidenceComplete := result.evidenceComplete
    issues := issues ++ result.issues
    unless sameMetadata job result.job do issues := issues.push "job metadata changed during execution"
    unless evidenceComplete do issues := issues.push "execution evidence is incomplete for this obligation"
  | [] => issues := issues.push "missing job observation"
  | _ => issues := issues.push "duplicate job observations"
  if job.role == .applicability then
    unless job.expected == .valid do issues := issues.push "applicability must expect Valid"
    unless job.applicability.isNone do issues := issues.push "applicability obligations cannot require another applicability obligation"
  let trustworthy := issues.isEmpty && evidenceComplete &&
    (observed == some .valid || observed == some .falsified)
  let mut status := Status.inconclusive
  if trustworthy then
    if job.role == .applicability then
      if observed == some .valid then status := .pass
      else issues := issues.push "no applicable scenario in this model"
    else
      status := match observed with
        | some .valid => if job.expected == .valid then .pass else .fail
        | some .falsified => if job.expected == .falsified then .pass else .fail
        | _ => .inconclusive
  else if issues.isEmpty then
    issues := issues.push (if job.role == .applicability then "applicability was not established"
      else "no conclusive property observation")
  return { row := { job, observed, status, issues, evidenceComplete }, trustworthy }

/-- Qualify properties using their explicit applicability links, then aggregate results. -/
def build (plan : GenerationPlan) (execution : Executor.Result) : Report := Id.run do
  let mut problems := execution.problems
  unless execution.state == .completed do
    problems := problems.push s!"execution did not complete: {reprStr execution.state}"
  if plan.jobs.isEmpty then problems := problems.push "no obligations were executed"
  let mut integrityProblems : Array String := #[]
  if plan.propertyDefinition != execution.propertyDefinition then
    integrityProblems := integrityProblems.push "property definition metadata changed during execution"
  if let .error message := plan.validateBindings then
    integrityProblems := integrityProblems.push s!"invalid model binding: {message}"
  if plan.jobs.isEmpty != (plan.status == .noObligations) then
    integrityProblems := integrityProblems.push "generation status and job count disagree"
  if execution.state == .noObligations && !plan.jobs.isEmpty then
    integrityProblems := integrityProblems.push "execution reports no obligations for a nonempty plan"
  if plan.jobs.any (fun job => (plan.jobs.filter (sameIdentity job)).size != 1) then
    integrityProblems := integrityProblems.push "duplicate requested job"
  if execution.jobs.any (fun result => !plan.jobs.any (sameIdentity result.job)) then
    integrityProblems := integrityProblems.push "execution contains observations for unrequested jobs"
  problems := problems ++ integrityProblems
  let observations := plan.jobs.map (observe execution (!integrityProblems.isEmpty))
  let mut rows := #[]
  for observation in observations do
    let mut row := observation.row
    if row.job.role == .property then
      if let some reference := row.job.applicability then
        let supports := observations.filter (fun support => matchesRef reference support.row.job)
        let reason := match supports.toList with
          | [support] =>
            if support.row.job.role != .applicability ||
                support.row.job.propertyId != row.job.propertyId then
              some "invalid applicability reference: expected an applicability obligation for this property"
            else if support.row.job.txModelId != row.job.txModelId ||
                support.row.job.binding != row.job.binding then
              some "invalid applicability reference: property and support use different model bindings"
            else if support.trustworthy && support.row.observed == some .valid then none
            else if support.trustworthy && support.row.observed == some .falsified then
              some "no applicable scenario in this model"
            else some "applicability was not established"
          | _ => some "invalid applicability reference: missing or ambiguous obligation"
        if let some reason := reason then
          row := { row with status := .inconclusive, issues := row.issues.push reason }
    rows := rows.push row
  let status := if rows.any (·.status == .fail) then Status.fail
    else if !problems.isEmpty || rows.isEmpty || rows.any (·.status == .inconclusive) then .inconclusive
    else .pass
  return { target := plan.targetName, status, rows, problems, notes := plan.notes
           evidenceDirectory := execution.directory, propertyDefinition := plan.propertyDefinition }

def failure (target message : String) (propertyDefinition : Option PropertyDefinition := none) : Report :=
  { target, status := .inconclusive, problems := #[message], propertyDefinition }

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
    ("statement", .str row.job.statement),
    ("role", .str row.job.role.label),
    ("txModelId", row.job.txModelId.map Json.str |>.getD .null),
    ("transactionModel", row.job.binding.map (fun binding => binding.txModel.toJson) |>.getD .null),
    ("combinedCheck", row.job.binding.map (fun binding => binding.combinedCheck.toJson) |>.getD .null),
    ("applicability", row.job.applicability.map (fun reference => Json.mkObj [
      ("module", .str reference.moduleName), ("name", .str reference.name)]) |>.getD .null),
    ("evidenceComplete", .bool row.evidenceComplete),
    ("expected", .str (expectedText row.job.expected)),
    ("observed", row.observed.map (fun value => Json.str (observedText value)) |>.getD .null),
    ("status", .str row.status.label), ("issues", Lean.toJson row.issues)]
  Json.mkObj [
    ("schemaVersion", Lean.toJson (1 : Nat)), ("target", .str report.target),
    ("status", .str report.status.label), ("exitCode", Lean.toJson report.exitCode.toNat),
    ("propertyDefinition", report.propertyDefinition.map (·.toJson) |>.getD .null),
    ("checks", .arr rows), ("problems", Lean.toJson report.problems), ("notes", Lean.toJson report.notes),
    ("evidenceDirectory", report.evidenceDirectory.map (fun path => Json.str path.toString) |>.getD .null)]

private def oneLine (text : String) : String :=
  text.replace "\r" "\\r" |>.replace "\n" "\\n" |>.replace "\t" "\\t"

private def definitionLabel : String → String
  | "schema_version" => "Metadata format"
  | "identity.id" => "Property"
  | "identity.definition_version" => "Definition version"
  | "identity.title" => "Title"
  | "identity.category" => "Category"
  | "explanation.summary" => "Description"
  | "explanation.claim" => "Claim"
  | "explanation.purpose" => "Purpose"
  | "scope.relevance_conditions" => "Relevance conditions"
  | "scope.preconditions" => "Definition premises"
  | "scope.limitations" => "Definition limitations"
  | "formalization.primary" => "Formal definition"
  | "formalization.theorems" => "Static theorem references"
  | label =>
    if label.startsWith "references[" then
      if label.endsWith ".label" then "Reference label" else "Reference"
    else label

private def modelLabel : String → String
  | "id" => "Model"
  | "title" => "Model title"
  | "plutus_version" => "Plutus version"
  | "description" => "Model description"
  | label => label

def Report.text (report : Report) : String := Id.run do
  let mut lines := #[s!"Target: {oneLine report.target}"]
  if let some definition := report.propertyDefinition then
    for (label, value) in definition.textFields do
      lines := lines.push s!"{oneLine (definitionLabel label)}: {oneLine value}"
  for row in report.rows do
    lines := lines.push s!"{row.status.label} {oneLine row.job.propertyId} {oneLine row.job.name}"
    if let some binding := row.job.binding then
      for (label, value) in binding.txModel.textFields do
        lines := lines.push s!"  {oneLine (modelLabel label)}: {oneLine value}"
      for (label, value) in binding.combinedCheck.textFields do
        if label == "limitations" then
          lines := lines.push s!"  Combination limitations: {oneLine value}"
    if let some issue := row.issues[0]? then
      lines := lines.push s!"  Reason: {oneLine issue}"
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
