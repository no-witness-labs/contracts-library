import PlutusCore.UPLC

/-! Execution helpers shared by generated blueprint types.
Extracted from fork PR #44 at 99a5734f0e036b6abfb4c3f121a298e35fa2eff6.
-/

namespace Formal.Universal.Properties

open PlutusCore.UPLC.Term (Program Term Const)
open PlutusCore.UPLC.CekMachine (State step initialState applyParams)

/-- CEK step bound used by generated checks; not a ledger CPU or memory budget. -/
abbrev ledgerFuel : Nat := 1000000

/-- `none` means the step bound was exhausted before a halt or error. -/
def runFor : State → Nat → Option State
  | .Halt v, _ => some (.Halt v)
  | .Error, _ => some .Error
  | _, 0 => none
  | s, n + 1 => runFor (step default s) n

/-- Error or a non-unit halt within `fuel` steps. Exhaustion is not rejection. -/
def rejectedWithin (p : Program) (args : List Term) (fuel : Nat) : Prop :=
  match p with
  | .Program _ body =>
      match runFor (initialState (applyParams body args)) fuel with
      | some .Error => True
      | some (.Halt v) => v ≠ .VCon Const.Unit
      | _ => False

end Formal.Universal.Properties
