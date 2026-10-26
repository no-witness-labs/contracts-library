/-
Linear vesting — the compiled validator, loaded once and shared.

`#import_uplc` reads the blueprint's `compiledCode`, copied there by `just verify` and `just vesting`
(gitignored). Keeping it in its own module lets both Soundness and Completeness state theorems
against the *same concrete* `spendValidator`. Proving `blaster` goals requires a concrete program —
an abstract `validator : Program` gives the SMT backend nothing to execute and makes proofs hang.
-/
import PlutusCore.UPLC

namespace Formal.Vesting.Linear.Script

open PlutusCore.UPLC.Term (Program)

#import_uplc linearVestingSpendScript PlutusV3 single_cbor_hex "Scripts/linear_vesting.linear_vesting.cbor"

/-- The compiled `spend` handler of `validators/linear_vesting.ak`. -/
def spendValidator : Program := linearVestingSpendScript.script

end Formal.Vesting.Linear.Script
