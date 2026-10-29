import Workflow.Tests.Unit.Generator.Tests
import Workflow.Tests.UP001.Tests
import Workflow.Tests.UP012.Tests

def main : IO Unit := do
  Workflow.Tests.Unit.Generator.run
  Workflow.Tests.UP001.Tests.run
  Workflow.Tests.UP012.Tests.run
  IO.println "Generator fixture checks passed."
