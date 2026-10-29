import Workflow.Tests.Support
import Workflow.Tests.UP001.Tests
import Formal.Universal.Properties

open Workflow.Tests.Support

def main : IO Unit := do
  Workflow.Tests.UP001.Tests.run
  let blueprint := "Workflow/Tests/UP001/Inputs/plutus.json"
  let passing ← invoke blueprint "vault.vault" (some "UP-001") 120000
    "UP001: passing validator" "PASS/0; five Valid results"
  expectOutcome "UP001 passing vault" passing "PASS" 0
  expectRows "UP001 passing vault" passing 5 "UP-001" "PASS" "valid" "5,000,000 CEK steps"
  expectArtifacts "UP001 passing vault" passing #["Types.lean", "Checks.lean"]
  let earlierReport ← IO.FS.readFile (passing.directory / "report.json")

  let failing ← invoke blueprint "vault_buggy.vault_buggy" (some "UP-001") 120000
    "UP001: deliberately failing validator" "FAIL/1; five Falsified results (intentional negative case)"
  expectOutcome "UP001 failing vault" failing "FAIL" 1
  expectRows "UP001 failing vault" failing 5 "UP-001" "FAIL" "falsified" "5,000,000 CEK steps"
  expectArtifacts "UP001 failing vault" failing #["Types.lean", "Checks.lean"]

  let invalid ← invoke "Workflow/Tests/UP001/Inputs/invalid-code.json" "invalid.invalid" (some "UP-001") 120000
    "UP001: invalid compiled code" "INCONCLUSIVE/2; intake rejection (intentional error case)"
  expectOutcome "invalid compiled code" invalid "INCONCLUSIVE" 2
  check "input failure has no proof observations" ((← rows invalid.report).isEmpty)
  expectProblem "invalid code fails during intake" invalid "compiledCode"

  let timeout ← invoke blueprint "vault.vault" none 1
    "UP001: forced one-millisecond timeout" "INCONCLUSIVE/2; exhausted execution budget (intentional timeout)"
  expectOutcome "shared execution deadline" timeout "INCONCLUSIVE" 2
  expectRows "default UP001 selection" timeout 5 "UP-001" "INCONCLUSIVE" "inconclusive" "5,000,000 CEK steps"
  expectArtifacts "shared execution deadline" timeout #["Types.lean", "Checks.lean"]
  expectProblem "timeout records exhausted execution budget" timeout "execution time budget exhausted"
  let directories := [passing.directory, failing.directory, invalid.directory, timeout.directory]
  check "whole-workflow runs remain isolated" (directories.eraseDups.length == directories.length)
  check "earlier report remains intact" ((← IO.FS.readFile (passing.directory / "report.json")) == earlierReport)
  IO.println "UP001 whole-workflow checks passed."
