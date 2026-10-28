import Workflow.Generator.OtherPurpose

namespace Workflow.Generator

/-- Register ordinary Lean providers here; the command entry point stays property-independent. -/
def providers : Array Provider := #[OtherPurpose.provider]

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

end Workflow.Generator
