import Workflow.Types
import Workflow.Jobs

namespace Workflow.Generator

inductive ErrorKind where
  | invalidNamespace | unsupported
  deriving BEq, Repr

structure Error where
  kind : ErrorKind
  message : String
  deriving Repr

instance : ToString Error where
  toString error := error.message

/-- Ordinary code supplying check-specific generation, with no file or process effects. -/
structure Provider where
  id : String
  generate : TargetDescription → String → Except Error GenerationPlan
  propertyDefinition : Option PropertyDefinition := none

/-- The caller chooses an isolated module prefix; generated code never writes it. -/
def generate (provider : Provider) (target : TargetDescription) (modulePrefix : String) :
    Except Error GenerationPlan := do
  unless validModuleName modulePrefix do
    throw ⟨.invalidNamespace, "module prefix must contain capitalized Lean identifier segments"⟩
  let plan ← provider.generate target modulePrefix
  return { plan with status := if plan.jobs.isEmpty then .noObligations else .ready
                     propertyDefinition := provider.propertyDefinition }

end Workflow.Generator
