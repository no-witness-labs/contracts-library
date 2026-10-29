import Workflow.Tests.Support
import Workflow.Tests.UP012.Tests

open Workflow.Tests.Support

def main : IO Unit := do
  Workflow.Tests.UP012.Tests.run
  let passing ← invoke "Workflow/Tests/UP012/Inputs/plutus.json" "linear_vesting.linear_vesting"
    (some "UP-012") 300000
  expectOutcome "original UP012 vesting suite" passing "PASS" 0
  expectRows "original UP012 vesting suite" passing 4 "UP-012" "PASS" "valid" "1,000,000-step bound"
  expectArtifacts "original UP012 vesting suite" passing #["Types.lean", "Tx.lean", "Checks.lean"]
  let checks ← rows passing.report
  let names ← checks.mapM (fun row => stringField row "name")
  check "UP012 preserves both property and applicability obligations"
    (names == #["dropSigner_claim", "dropSigner_claim_applies", "dropSigner_cancel", "dropSigner_cancel_applies"])
  let unsupported ← invoke "Workflow/Tests/UP012/Inputs/unsupported.json" "unsupported.validator"
    (some "UP-012") 300000
  expectOutcome "unsupported UP012 artifact" unsupported "INCONCLUSIVE" 2
  check "unsupported profile has no proof observations" ((← rows unsupported.report).isEmpty)
  expectProblem "UP012 rejects unsupported profile" unsupported "original unparameterized"
  check "UP012 attempts have separate output directories" (passing.directory != unsupported.directory)
  IO.println "UP012 whole-workflow checks passed."
