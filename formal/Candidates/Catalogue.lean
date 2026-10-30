import Candidates.UP001
import Workflow.PropertyDefinition
import Workflow.Tests.UP012.Profile

namespace Candidates.Catalogue

open Workflow.Generator

private structure Registration where
  provider : Provider
  definitionVersion : Int
  primary : String

private def registrations : Array Registration := #[
  { provider := Candidates.UP001.provider
    definitionVersion := 1
    primary := "Candidates.UP001.statement" },
  { provider := Workflow.Tests.UP012.Profile.provider
    definitionVersion := 1
    primary := "Candidates.UP012.checks" }]

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

/-- Load the workflow's maintained metadata without changing pure provider selection. -/
def loadProvider (id : Option String) : IO (Except String Provider) := do
  if let .error message := selectRegistration id then return .error message
  let path : System.FilePath := "Candidates/property-definitions.json"
  let definitions ← match ← Workflow.PropertyDefinition.read path with
    | .ok value => pure value
    | .error message => return .error message
  return (withDefinitions id definitions).mapError fun message => s!"{path}: {message}"

end Candidates.Catalogue
