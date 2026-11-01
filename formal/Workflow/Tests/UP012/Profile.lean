import Workflow.Tests.Profiles.LinearVesting
import Workflow.Tests.Profiles.Vault
import Candidates.UP012

namespace Workflow.Tests.UP012.Profile

open Workflow Workflow.Generator

/-! Pinned vesting and vault scenarios use the shared UP-012 property and applicability goals.
Preparation accepts exact supported artifacts and emits native transaction aliases.
-/

private def buildSelected (target : TargetDescription) (modulePrefix : String)
    (selectedModelId : Option String) : Except Error GenerationPlan := do
  let (modules, modelId) ← match selectedModelId with
    | some modelId => do
      let modules ← if modelId == Formal.TxModels.TxM009.metadata.id then
          Workflow.Tests.Profiles.Vault.support target modulePrefix
        else Workflow.Tests.Profiles.LinearVesting.support target modulePrefix (some modelId)
      pure (modules, some modelId)
    | none =>
      match Workflow.Tests.Profiles.Vault.support target modulePrefix with
      | .ok modules => pure (modules, some Formal.TxModels.TxM009.metadata.id)
      | .error vaultError =>
        match Workflow.Tests.Profiles.LinearVesting.support target modulePrefix none with
        | .ok modules => pure (modules, none)
        | .error vestingError =>
          throw ⟨.unsupported, s!"{vestingError.message}; {vaultError.message}"⟩
  let checks ← match modelId with
    | none => pure (Candidates.UP012.checks modulePrefix)
    | some id => Candidates.UP012.checksForModel id modulePrefix
  let jobs ← match modelId with
    | none => pure (Candidates.UP012.jobs modulePrefix)
    | some id => Candidates.UP012.jobsForModel id modulePrefix
  return {
    targetName := target.name
    modules := modules.push checks
    jobs
    notes := match modelId with
      | none => Candidates.UP012.notes
      | some id => Candidates.UP012.notesForModel id }

/-- Select the exact supported artifact family and its bounded experimental checks. -/
def provider : Provider := { id := "UP-012", generate := fun target modulePrefix => buildSelected target modulePrefix none }

/-- Bind one native action model to its exact artifact guard. -/
def providerForModel (selectedModelId : String) : Except Error Provider := do
  unless Candidates.UP012.modelIds.contains selectedModelId do
    throw ⟨.unsupported, s!"UP-012 has no registered model {selectedModelId}"⟩
  return { id := "UP-012", generate := fun target modulePrefix => buildSelected target modulePrefix (some selectedModelId) }

end Workflow.Tests.UP012.Profile
