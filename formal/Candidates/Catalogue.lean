import Candidates.UP001
import Workflow.Tests.UP012.Profile

namespace Candidates.Catalogue

open Workflow.Generator

/-- Compose the currently runnable candidate implementations and experimental profiles. -/
def providers : Array Provider := #[Candidates.UP001.provider, Workflow.Tests.UP012.Profile.provider]

def selectProvider (id : Option String) : Except String Provider :=
  match id with
  | none =>
    match providers[0]? with
    | some provider => .ok provider
    | none => .error "no check providers are registered"
  | some name =>
    match providers.find? (·.id == name) with
    | some provider => .ok provider
    | none => .error s!"unsupported check provider: {name}"

end Candidates.Catalogue
