import Workflow.Generator.Basic
import Workflow.Types.Check

namespace Workflow.Generator

/-- One code-owned generator and its exact resolved descriptive binding. -/
structure ConfiguredCheck where
  context : CheckContext
  generate : TargetDescription → String → Except Error GenerationPlan

def generateOne (check : ConfiguredCheck) (target : TargetDescription)
    (modulePrefix : String) : Except Error GenerationPlan := do
  check.context.validate target |>.mapError fun message => { kind := .unsupported, message }
  let provider : Provider := {
    id := check.context.propertyDefinition.id?.getD ""
    generate := check.generate
    propertyDefinition := some check.context.propertyDefinition
    bindings := some #[check.context.binding] }
  let plan ← Generator.generate provider target modulePrefix
  check.context.validatePlan target plan |>.mapError fun message => { kind := .unsupported, message }
  return plan

end Workflow.Generator
