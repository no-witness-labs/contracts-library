import Candidates.UP001
import Workflow.PropertyDefinition
import Workflow.Tests.UP012.Profile
import Formal.TxModels.Index
import Formal.Properties.Index

namespace Candidates.Catalogue

open Workflow.Generator

private structure Registration where
  provider : Provider
  entry : Formal.Properties.Entry
  modelIds : Array String
  checksPath : System.FilePath

private def registrations : Array Registration := #[
  { provider := Candidates.UP001.provider
    entry := Formal.Properties.Universal.Index.up001
    modelIds := Candidates.UP001.modelIds
    checksPath := "Candidates/combined-checks.json" },
  { provider := Workflow.Tests.UP012.Profile.provider
    entry := Formal.Properties.Universal.Index.up012
    modelIds := Candidates.UP012.modelIds
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
  unless registration.provider.id == registration.entry.id do
    throw "property index and registered provider IDs disagree"
  let matchingDefinitions := definitions.filter fun definition =>
    definition.id? == some registration.provider.id &&
    definition.version? == some registration.entry.definitionVersion
  let description := s!"property definition {registration.provider.id} version {registration.entry.definitionVersion}"
  let some definition := matchingDefinitions[0]?
    | throw s!"{description} is missing from the catalogue"
  if matchingDefinitions.size != 1 then
    throw s!"{description} occurs more than once in the catalogue"
  if let some primary := definition.primary? then
    unless primary == registration.entry.primary.toString do
      throw s!"{description} primary does not match the registered declaration {registration.entry.primary.toString}"
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
  let path := registration.entry.metadataPath
  let definition ← match ← Workflow.PropertyDefinition.readRecord path with
    | .ok value => pure value
    | .error message => return .error message
  let provider ← match withDefinitions id #[definition] with
    | .ok value => pure value
    | .error message => return .error s!"{path}: {message}"
  let models ← match Workflow.TransactionModel.parseList Formal.TxModels.Index.toJson with
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
        s!"Formal.TxModels.Index, {registration.checksPath}: {message}"
    return { provider with bindings := some bindings }

end Candidates.Catalogue
