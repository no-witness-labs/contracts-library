-- The honest transactions for the H checks in `Honest.lean`: for each action, a shape, that is a
-- transaction with a fixed structure whose leaves are the fields of a structure. Written once by
-- process_blueprint.py as a stub; it is never replaced, so edit it freely.
import CardanoLedgerApi
import Formal.Universal.TxBuilder
import Formal.Vesting.Linear.Blueprint.Types

namespace Formal.Vesting.Linear.Blueprint

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V3 (ScriptContext TxInInfo)
open Formal.Universal.TxBuilder

/-- The datum: one vested asset, key credentials for the beneficiary and the locker. The policy is
    the literal "policyA" everywhere: with a symbolic policy, Blaster stops inside
    `validScriptContext` with "Inductive datatype with instance parameters not supported". -/
def vestingDatum (beneficiary locker name : ByteString) (total start finish recovery : Int) : Data :=
  IsData.toData
    ({ beneficiary := .PubKeyCredential beneficiary
       locker := .PubKeyCredential locker
       vesting := [{ policy := "policyA", name := name, total := total }]
       start_time := start
       end_time := finish
       recovery_time := recovery } : Vesting.Types.VestingDatum)

/-! ## Claim: 2 inputs (the vesting position, the signer's fee input), 2 outputs (the continuation,
the payout to the signer), 1 signatory. -/

structure ClaimLeaves where
  beneficiary : ByteString
  locker : ByteString
  name : ByteString
  total : Int
  start : Int
  finish : Int
  recovery : Int
  script : ByteString
  prevTx : ByteString
  txId : ByteString
  scriptAda : Int
  feeInputAda : Int
  keptAda : Int
  kept : Int
  fee : Int
  now : Int
  signer : ByteString

def honest_spend_Claim (p : ClaimLeaves) : ScriptContext :=
  let datum := vestingDatum p.beneficiary p.locker p.name p.total p.start p.finish p.recovery
  let own : TxInInfo := ⟨⟨p.prevTx, 0⟩, toScript p.script (adaAnd p.scriptAda "policyA" p.name p.total) datum⟩
  let feeInput : TxInInfo := ⟨⟨p.prevTx, 1⟩, toKey p.signer (ada p.feeInputAda)⟩
  spend own [feeInput]
    [ toScript p.script (adaAnd p.keptAda "policyA" p.name p.kept) datum,
      toKey p.signer
        (adaAnd (p.scriptAda + p.feeInputAda - p.keptAda - p.fee) "policyA" p.name (p.total - p.kept)) ]
    [p.signer] p.now p.fee p.txId (IsData.toData Vesting.Types.VestingRedeemer.Claim)

/-! ## Cancel: 2 inputs (the vesting position, the signer's fee input), 1 output (everything to the
signer), 1 signatory. -/

structure CancelLeaves where
  beneficiary : ByteString
  locker : ByteString
  name : ByteString
  total : Int
  start : Int
  finish : Int
  recovery : Int
  script : ByteString
  prevTx : ByteString
  txId : ByteString
  scriptAda : Int
  feeInputAda : Int
  fee : Int
  now : Int
  signer : ByteString

def honest_spend_Cancel (p : CancelLeaves) : ScriptContext :=
  let datum := vestingDatum p.beneficiary p.locker p.name p.total p.start p.finish p.recovery
  let own : TxInInfo := ⟨⟨p.prevTx, 0⟩, toScript p.script (adaAnd p.scriptAda "policyA" p.name p.total) datum⟩
  let feeInput : TxInInfo := ⟨⟨p.prevTx, 1⟩, toKey p.signer (ada p.feeInputAda)⟩
  spend own [feeInput]
    [ toKey p.signer (adaAnd (p.scriptAda + p.feeInputAda - p.fee) "policyA" p.name p.total) ]
    [p.signer] p.now p.fee p.txId (IsData.toData Vesting.Types.VestingRedeemer.Cancel)

end Formal.Vesting.Linear.Blueprint
