import Workflow.PropertyDefinition

namespace Workflow

private def asciiLetter (c : Char) : Bool :=
  ('A' ≤ c && c ≤ 'Z') || ('a' ≤ c && c ≤ 'z')

private def moduleSegment (segment : String) : Bool :=
  match segment.data with
  | [] => false
  | first :: rest =>
    'A' ≤ first && first ≤ 'Z' &&
      rest.all (fun c => asciiLetter c || c.isDigit || c == '_') &&
      !["Type", "Prop", "Sort"].contains segment

/-- Module names accepted by generation and isolated artifact writing. -/
def validModuleName (name : String) : Bool :=
  (name.splitOn ".").all moduleSegment

inductive ExpectedResult where
  | valid | falsified
  deriving BEq, Repr

structure GeneratedModule where
  name : String
  source : String

inductive JobRole where
  | property | applicability
  deriving BEq, Repr

def JobRole.label : JobRole → String
  | .property => "property"
  | .applicability => "applicability"

/-- A reference to one obligation in the current generation plan. -/
structure JobRef where
  moduleName : String
  name : String
  deriving BEq, Repr

/-- A job declares its expectation; downstream code need not interpret property IDs. -/
structure CheckJob where
  propertyId : String
  name : String
  moduleName : String
  statement : String
  expected : ExpectedResult
  scope : String
  role : JobRole := .property
  applicability : Option JobRef := none

inductive GenerationStatus where
  | ready | noObligations
  deriving BEq, Repr

structure GenerationPlan where
  targetName : String
  modules : Array GeneratedModule
  jobs : Array CheckJob
  notes : Array String := #[]
  status : GenerationStatus := .ready
  propertyDefinition : Option PropertyDefinition := none

end Workflow
