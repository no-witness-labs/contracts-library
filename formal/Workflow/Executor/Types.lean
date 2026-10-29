import Lean.Data.Json
import Workflow.Jobs

namespace Workflow.Executor

inductive ProcessState where
  | finished | timedOut | launchError
  deriving BEq, Repr

structure ProcessObservation where
  state : ProcessState
  exitCode : Option UInt32 := none
  stdout : String := ""
  stderr : String := ""
  elapsedMs : Nat := 0

structure Diagnostic where
  fileName : String
  line : Nat
  column : Nat
  severity : String
  message : String

inductive ObservedResult where
  | valid | falsified | inconclusive
  deriving BEq, Repr

structure JobObservation where
  job : CheckJob
  observed : ObservedResult := .inconclusive
  /-- The module finished with intact evidence; local job issues remain separate. -/
  evidenceComplete : Bool := false
  diagnostics : Array Diagnostic := #[]
  issues : Array String := #[]

structure ModuleObservation where
  name : String
  path : System.FilePath
  process : ProcessObservation

inductive RunState where
  | completed | timedOut | error | noObligations
  deriving BEq, Repr

structure Result where
  state : RunState
  directory : Option System.FilePath := none
  modules : Array ModuleObservation := #[]
  jobs : Array JobObservation := #[]
  problems : Array String := #[]
  elapsedMs : Nat := 0

structure Options where
  /-- Prepared dependency/module search path; preparation is the caller's responsibility. -/
  leanPath : String
  leanCommand : String := "lean"
  timeoutCommand : String := "timeout"
  /-- Parent for fresh run directories; none uses the system temporary directory. -/
  outputRoot : Option System.FilePath := none
  /-- One shared wall-clock budget across generated modules. -/
  budgetMs : Nat := 30000

end Workflow.Executor
