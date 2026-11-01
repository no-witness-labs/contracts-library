import Workflow.Tests.Profiles.LinearVesting
import Candidates.UP012

namespace Workflow.Tests.UP012.Profile

open Workflow Workflow.Generator

/-! Experimental vesting scenario from PR #55 at f5cbda7df624f2496dd2e6fe354a0cd15365b923.
Shared test preparation guards the original artifact and emits native type and model aliases.
The candidate module supplies the single authoritative set of four propositions.
-/

private def buildSelected (target : TargetDescription) (modulePrefix : String)
    (selectedModelId : Option String) : Except Error GenerationPlan := do
  let modules ← Workflow.Tests.Profiles.LinearVesting.support target modulePrefix selectedModelId
  let checks ← match selectedModelId with
    | none => pure (Candidates.UP012.checks modulePrefix)
    | some modelId => Candidates.UP012.checksForModel modelId modulePrefix
  let jobs ← match selectedModelId with
    | none => pure (Candidates.UP012.jobs modulePrefix)
    | some modelId => Candidates.UP012.jobsForModel modelId modulePrefix
  return {
    targetName := target.name
    modules := modules.push checks
    jobs
    notes := Candidates.UP012.notes }

/-- Run the original vesting candidate as a bounded experimental profile. -/
def provider : Provider := { id := "UP-012", generate := fun target modulePrefix => buildSelected target modulePrefix none }

/-- Bind the pinned fixture to one action model without changing its target guard. -/
def providerForModel (selectedModelId : String) : Except Error Provider := do
  unless Candidates.UP012.modelIds.contains selectedModelId do
    throw ⟨.unsupported, s!"UP-012 has no registered model {selectedModelId}"⟩
  return { id := "UP-012", generate := fun target modulePrefix => buildSelected target modulePrefix (some selectedModelId) }

end Workflow.Tests.UP012.Profile
