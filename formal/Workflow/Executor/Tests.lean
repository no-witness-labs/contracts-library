import Workflow.Executor

open Lean Workflow

namespace Workflow.Executor.Tests

private def check (label : String) (condition : Bool) : IO Unit := do
  unless condition do throw (IO.userError s!"FAIL: {label}")

private def plan (mode : String) : GenerationPlan :=
  { targetName := "fixture", modules := #[⟨"Fixture.Checks",
      s!"-- {mode}\n\ntheorem fixture : True := by trivial\n"⟩]
    jobs := #[{ propertyId := "fixture", name := "fixture", moduleName := "Fixture.Checks",
                statement := "True", expected := .valid, scope := "fixture only" }] }

private def emit (path message : String) (severity := "information") (line := 3) (column := 0) : IO Unit := do
  let output ← IO.getStdout
  output.putStrLn (Json.mkObj [
    ("fileName", .str path), ("data", .str message), ("severity", .str severity),
    ("pos", Json.mkObj [("line", toJson line), ("column", toJson column)])]).compress
  output.flush

/-- The test executable also acts as a controlled compiler for isolated process tests. -/
def compiler (args : List String) : IO UInt32 := do
  let path : System.FilePath := args.getLast!
  let mode := ((← IO.FS.readFile path).splitOn "\n").head!.drop 3
  match mode with
  | "valid" => emit path.toString "✅ Valid"; return 0
  | "warning" =>
    emit path.toString "declaration uses 'blasterProven' (SMT-verified, no proof term)" "warning"
    return 0
  | "falsified" =>
    emit path.toString "❌ Falsified" "error"
    emit path.toString "Counterexample:" "error"
    emit path.toString "- x: 1" "error"
    emit path.toString " - r: (Data.B\n  (ByteString.mk \"value\"))" "error"
    emit path.toString "Tactic `blaster` failed: Goal was falsified (see counterexample above)\n\n⊢ False" "error"
    return 1
  | "unexpected-valid" => emit path.toString "❌ Unexpected Valid" "error"; return 1
  | "foreign" => emit "/foreign.lean" "✅ Valid"; return 0
  | "off-range" => emit path.toString "✅ Valid" "information" 99; return 0
  | "malformed-json" =>
    emit path.toString "✅ Valid"
    (← IO.getStdout).putStrLn "{"
    return 0
  | "foreign-error" =>
    emit path.toString "✅ Valid"
    emit "/foreign.lean" "unknown identifier" "error"
    return 1
  | "error-after" | "zero-error" =>
    emit path.toString "✅ Valid"
    emit path.toString "unknown identifier 'broken'" "error"
    return if mode == "zero-error" then 0 else 1
  | "conflict" =>
    emit path.toString "✅ Valid"
    emit path.toString "❌ Falsified" "error"
    return 1
  | "wrong-detail-position" =>
    emit path.toString "❌ Falsified" "error"
    emit path.toString "Counterexample:" "error" 3 8
    return 1
  | "wrong-indented-detail-position" =>
    emit path.toString "❌ Falsified" "error"
    emit path.toString " - r: 1" "error" 3 8
    return 1
  | "orphan-detail" =>
    emit path.toString "✅ Valid"
    emit path.toString " - r: 1" "error"
    return 1
  | "sorry" | "undetermined" =>
    emit path.toString "✅ Valid"
    emit path.toString (if mode == "sorry" then "declaration uses 'sorry'" else "⚠️ Undetermined") "warning"
    return 0
  | "exit-one" => return 1
  | "delay" => IO.sleep 400; return 0
  | "late-valid" => IO.sleep 400; emit path.toString "✅ Valid"; return 0
  | "partial" => emit path.toString "✅ Valid"; IO.sleep 60000; return 0
  | "timeout" =>
    let _ ← IO.Process.spawn {
      cmd := (← IO.appPath).toString
      args := #["--child", (path.withExtension "child.pid").toString]
      stdin := .null }
    IO.sleep 60000
    return 0
  | _ => return 0

private def withResult (input : GenerationPlan) (options : Options) (f : Result → IO Unit) : IO Unit := do
  match ← Executor.run input options with
  | .error message => throw (IO.userError message)
  | .ok result =>
    try f result
    finally
      if let some directory := result.directory then IO.FS.removeDirAll directory

private def firstJob (result : Result) : IO JobObservation :=
  match result.jobs[0]? with
  | some value => pure value
  | none => throw (IO.userError "missing job observation")

def run : IO Unit := do
  let options : Options := { leanPath := ".", leanCommand := (← IO.appPath).toString, budgetMs := 5000 }
  for mode in ["valid", "warning", "falsified", "unexpected-valid"] do
    withResult (plan mode) options fun result => do
      let job ← firstJob result
      check s!"{mode}: execution completed" (result.state == .completed)
      check s!"{mode}: observed solver outcome" (job.observed ==
        if mode == "falsified" then .falsified else .valid)
      check s!"{mode}: expectation preserved" (job.job.expected == .valid)
      let some directory := result.directory | throw (IO.userError "missing evidence directory")
      check "manifest retained" (← (directory / "execution.json").pathExists)
      check "source retained" (← (directory / "Fixture/Checks.lean").pathExists)
      check "raw diagnostics retained" (← (directory / "Fixture/Checks.stdout.log").pathExists)
  for mode in ["silent", "foreign", "off-range", "malformed-json", "foreign-error", "error-after", "zero-error", "conflict",
      "wrong-detail-position", "wrong-indented-detail-position", "orphan-detail", "sorry", "undetermined", "exit-one"] do
    withResult (plan mode) options fun result => do
      let job ← firstJob result
      check s!"{mode}: no false conclusive outcome"
        (result.state == .error && job.observed == .inconclusive && !result.problems.isEmpty)
  withResult (plan "valid") { options with leanCommand := "/missing/lean" } fun result => do
    check "missing compiler is an execution problem" (result.state == .error)
  withResult (plan "valid") { options with timeoutCommand := "/missing/timeout" } fun result => do
    check "missing supervisor is an execution problem" (result.state == .error)
  for mode in ["timeout", "partial"] do
    withResult (plan mode) { options with budgetMs := 700 } fun result => do
      let job ← firstJob result
      check s!"{mode}: bounded and inconclusive"
        (result.state == .timedOut && job.observed == .inconclusive && result.elapsedMs < 3000)
      if mode == "partial" then
        check "partial positive evidence retained" (job.diagnostics.any (·.message == "✅ Valid"))
      else
        let some directory := result.directory | throw (IO.userError "missing timeout evidence")
        let pid ← IO.FS.readFile (directory / "Fixture/Checks.child.pid")
        IO.sleep 30
        let process : System.FilePath := s!"/proc/{pid.trim}/status"
        if ← process.pathExists then
          let status ← IO.FS.readFile process
          check "descendant is no longer running" ((status.splitOn "State:\tZ").length > 1)
  let shared := { plan "late-valid" with modules :=
    #[⟨"Fixture.Support", "-- delay\n"⟩] ++ (plan "late-valid").modules }
  withResult shared { options with budgetMs := 700 } fun result => do
    check "budget is shared across modules" (result.state == .timedOut && result.modules.size == 2)
  let empty : GenerationPlan := { targetName := "fixture", modules := #[], jobs := #[], status := .noObligations }
  withResult empty { options with leanCommand := "/missing/lean" } fun result => do
    check "empty plan does not launch a compiler or pass" (result.state == .noObligations && result.directory.isNone)
  for invalid in [
      { plan "valid" with modules := #[⟨"../Escape", ""⟩] },
      { plan "valid" with modules := #[] },
      { plan "valid" with status := .noObligations },
      { plan "valid" with jobs := (plan "valid").jobs ++ (plan "valid").jobs },
      { plan "valid" with modules := #[⟨"Fixture.Checks", "def different := 1\n"⟩] }] do
    match ← Executor.run invalid options with
    | .error _ => pure ()
    | .ok _ => throw (IO.userError "invalid plan accepted")
  match ← Executor.run (plan "valid") { options with budgetMs := 0 } with
  | .error _ => pure ()
  | .ok _ => throw (IO.userError "zero budget accepted")
  IO.println "Executor fixture checks passed."

end Workflow.Executor.Tests

def main (args : List String) : IO UInt32 := do
  match args with
  | ["--child", path] =>
    IO.FS.writeFile path (toString (← IO.Process.getPID))
    IO.sleep 60000
    return 0
  | _ =>
    if args.contains "--json" then Workflow.Executor.Tests.compiler args
    else Workflow.Executor.Tests.run *> pure 0
