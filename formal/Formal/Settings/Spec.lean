import CardanoLedgerApi.V2.Tx

namespace Formal.Settings.Spec

open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V1.Value (lovelaceOf withoutLovelace)
open CardanoLedgerApi.V2.Tx (TxOut)
open PlutusCore.Data (Data)

/-- Decoded datum for the reference Settings validator at IO commit `42048b7`. -/
structure SettingsDatum where
  current : Data
  next : Option Data
  nextApply : Option Int

/-- Encode the datum using the constructor and field order in `settings/types.ak`. -/
def datumData (datum : SettingsDatum) : Data :=
  .Constr 0 [datum.current, IsData.toData datum.next, IsData.toData datum.nextApply]

/--
The transaction fields used by `Apply` after decoding. The caller resolves
the own input and the output at the redeemer index and evaluates the applier
credential. The value helpers assume canonical ledger output values.
-/
structure ApplyContext where
  validityLowerBound : Option Int
  applierAuthorized : Bool
  spendingOutput : Option TxOut
  continuation : Option TxOut

/-- The reference validator's `Apply` rule for the projected context. -/
def applyAccepts (datum : Option SettingsDatum) (ctx : ApplyContext) : Bool :=
  match datum, ctx.validityLowerBound, ctx.spendingOutput, ctx.continuation with
  | some state, some now, some spent, some next =>
    match state.next, state.nextApply, spent.txOutAddress.addressCredential with
    | some pending, some readyAt, .ScriptCredential _ =>
      let applied : SettingsDatum := { current := pending, next := none, nextApply := none }
      ctx.applierAuthorized &&
        decide (readyAt ≤ now) &&
        next.txOutAddress == spent.txOutAddress &&
        withoutLovelace next.txOutValue == withoutLovelace spent.txOutValue &&
        decide (lovelaceOf spent.txOutValue ≤ lovelaceOf next.txOutValue) &&
        next.txOutDatum == .OutputDatum (datumData applied) &&
        next.txOutReferenceScript.isNone
    | _, _, _ => false
  | _, _, _, _ => false

end Formal.Settings.Spec
