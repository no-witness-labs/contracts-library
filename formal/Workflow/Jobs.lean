namespace Workflow

inductive ExpectedResult where
  | valid | falsified
  deriving BEq, Repr

structure GeneratedModule where
  name : String
  source : String

/-- A job declares its expectation; downstream code need not interpret property IDs. -/
structure CheckJob where
  propertyId : String
  name : String
  moduleName : String
  statement : String
  expected : ExpectedResult
  scope : String

inductive GenerationStatus where
  | ready | noObligations
  deriving BEq, Repr

structure GenerationPlan where
  targetName : String
  modules : Array GeneratedModule
  jobs : Array CheckJob
  notes : Array String := #[]
  status : GenerationStatus := .ready

end Workflow
