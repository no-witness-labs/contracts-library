import Candidates.UP001
import Workflow.PropertyDefinition
import Workflow.Tests.UP012.Profile

namespace Candidates.Catalogue

open Workflow.Generator

private structure Registration where
  provider : Provider
  definitionVersion : Int
  primary : String
  modelIds : Array String
  modelsPath : System.FilePath
  checksPath : System.FilePath

private def registrations : Array Registration := #[
  { provider := Candidates.UP001.provider
    definitionVersion := 1
    primary := "Candidates.UP001.statement"
    modelIds := Candidates.UP001.modelIds
    modelsPath := "Candidates/transaction-models.json"
    checksPath := "Candidates/combined-checks.json" },
  { provider := Workflow.Tests.UP012.Profile.provider
    definitionVersion := 1
    primary := "Candidates.UP012.checks"
    modelIds := Candidates.UP012.modelIds
    modelsPath := "Workflow/Tests/UP012/transaction-models.json"
    checksPath := "Workflow/Tests/UP012/combined-checks.json" }]

/-- Compose the currently runnable candidate implementations and experimental profiles. -/
def providers : Array Provider := registrations.map (·.provider)

private def selectRegistration (id : Option String) : Except String Registration :=
  match id with
  | none =>
    match registrations[0]? with
    | some registration => .ok registration
    | none => .error "no check providers are registered"
  | some name =>
    match registrations.find? (·.provider.id == name) with
    | some registration => .ok registration
    | none => .error s!"unsupported check provider: {name}"

def selectProvider (id : Option String) : Except String Provider :=
  (selectRegistration id).map (·.provider)

/-- Associate supplied records with the fixed implementation; metadata cannot select code. -/
def withDefinitions (id : Option String) (definitions : Array Workflow.PropertyDefinition) :
    Except String Provider := do
  let registration ← selectRegistration id
  let matchingDefinitions := definitions.filter fun definition =>
    definition.id? == some registration.provider.id &&
    definition.version? == some registration.definitionVersion
  let description := s!"property definition {registration.provider.id} version {registration.definitionVersion}"
  let some definition := matchingDefinitions[0]?
    | throw s!"{description} is missing from the catalogue"
  if matchingDefinitions.size != 1 then
    throw s!"{description} occurs more than once in the catalogue"
  if let some primary := definition.primary? then
    unless primary == registration.primary do
      throw s!"{description} primary does not match the registered declaration {registration.primary}"
  return { registration.provider with propertyDefinition := some definition }

/-- Bind maintained descriptions to the models used by the fixed implementation. -/
def withBindings (id : Option String) (definitions : Array Workflow.PropertyDefinition)
    (models : Array Workflow.TransactionModel) (checks : Array Workflow.CombinedCheck) :
    Except String Provider := do
  let registration ← selectRegistration id
  let provider ← withDefinitions id definitions
  let some definition := provider.propertyDefinition
    | throw "selected provider has no property definition"
  let bindings ← registration.modelIds.mapM fun modelId =>
    Workflow.CheckBinding.resolve definition modelId models checks
  return { provider with bindings := some bindings }

/-- Load the workflow's maintained metadata without changing pure provider selection. -/
def loadProvider (id : Option String) : IO (Except String Provider) := do
  let registration ← match selectRegistration id with
    | .ok value => pure value
    | .error message => return .error message
  let path : System.FilePath := "Candidates/property-definitions.json"
  let definitions ← match ← Workflow.PropertyDefinition.read path with
    | .ok value => pure value
    | .error message => return .error message
  let provider ← match withDefinitions id definitions with
    | .ok value => pure value
    | .error message => return .error s!"{path}: {message}"
  let models ← match ← Workflow.TransactionModel.read registration.modelsPath with
    | .ok value => pure value
    | .error message => return .error message
  let checks ← match ← Workflow.CombinedCheck.read registration.checksPath with
    | .ok value => pure value
    | .error message => return .error message
  let some definition := provider.propertyDefinition
    | return .error "selected provider has no property definition"
  return do
    let bindings ← registration.modelIds.mapM fun modelId =>
      (Workflow.CheckBinding.resolve definition modelId models checks).mapError fun message =>
        s!"{registration.modelsPath}, {registration.checksPath}: {message}"
    return { provider with bindings := some bindings }

end Candidates.Catalogue
