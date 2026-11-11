import Blaster
import CardanoLedgerApi.V3
import Formal.Vesting.Linear.SpecNew
import Formal.Vesting.Linear.Cancel

namespace Formal.Vesting.Linear.Claim

open PlutusCore.Data (Data)
open PlutusCore.Integer (Integer)
open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V1.Value (CurrencySymbol TokenName)
open CardanoLedgerApi.V3
  (Credential POSIXTimeRange PubKeyHash ScriptContext ScriptHash TxInInfo TxInfo TxOut TxOutRef)
open Formal.Vesting.Linear.SpecNew (VestedAsset VestingDatum datumData redeemerData)
open Formal.Vesting.Linear.Cancel (Agrees)

/-- Another input at a script address, with any datum and value. -/
structure ClaimIn where
  ref        : TxOutRef
  scriptHash : ScriptHash
  datum      : Data
  value      : List (Data × Data)

def ClaimIn.toTxInInfo (i : ClaimIn) : TxInInfo :=
  ⟨i.ref, ⟨⟨.ScriptCredential i.scriptHash, none⟩, i.value, .OutputDatum i.datum, none⟩⟩

/-- An output at a script address, with any datum and one asset. -/
structure ClaimOut where
  scriptHash : ScriptHash
  datum      : Data
  policy     : CurrencySymbol
  name       : TokenName
  qty        : Integer

def ClaimOut.toTxOut (o : ClaimOut) : TxOut :=
  ⟨⟨.ScriptCredential o.scriptHash, none⟩,
   [(Data.B o.policy, Data.Map [(Data.B o.name, Data.I o.qty)])],
   .OutputDatum o.datum, none⟩

/-- A claim transaction: the vesting input being spent, put first among the inputs,
the other inputs and the outputs, and everything else left arbitrary. -/
structure ClaimTx where
  datum       : VestingDatum
  ownRef      : TxOutRef
  scriptHash  : ScriptHash
  ownValue    : List (Data × Data)
  range       : POSIXTimeRange
  signatories : List PubKeyHash
  withdrawals : List (Credential × Integer)
  otherInputs : List ClaimIn
  outputs     : List ClaimOut
  rest        : TxInfo

def ClaimTx.ctx (tx : ClaimTx) : ScriptContext :=
  { scriptContextTxInfo :=
      { tx.rest with
        txInfoInputs :=
          ⟨tx.ownRef,
            ⟨⟨.ScriptCredential tx.scriptHash, none⟩, tx.ownValue,
             .OutputDatum (datumData tx.datum), none⟩⟩ ::
          tx.otherInputs.map ClaimIn.toTxInInfo
        txInfoOutputs := tx.outputs.map ClaimOut.toTxOut
        txInfoWdrl := tx.withdrawals
        txInfoValidRange := IsData.toData tx.range
        txInfoSignatories := tx.signatories }
    scriptContextRedeemer := redeemerData .claim
    scriptContextScriptInfo := .SpendingScript tx.ownRef (some (datumData tx.datum)) }

def claimAgreesOn (tx : ClaimTx) : Prop := Agrees tx.datum .claim tx.ctx

theorem claim_agrees
    (tx : ClaimTx) (bh : PubKeyHash) (asset : VestedAsset)
    (hB : tx.datum.beneficiary = .PubKeyCredential bh)
    (hV : tx.datum.vesting = [asset])
    (hU : tx.range.ivTo = .InfiniteUpperBound .PosInf)
    (hSig : tx.signatories.length < 2)
    (hIn : tx.otherInputs.length < 2)
    (hOut : tx.outputs.length < 4) :
    claimAgreesOn tx := by
  rcases tx with
    ⟨⟨bene, locker, vesting, start, finish, recovery⟩, ownRef, sh, ownValue, ⟨low, up⟩,
      sigs, wdrl, ins, outs, rest⟩
  simp only at hB hV hU hSig hIn hOut
  subst hB hV hU
  unfold claimAgreesOn Agrees
  rcases low with ⟨now, c⟩ | b
  · rcases sigs with _ | ⟨s, _ | ⟨_, _⟩⟩
    · -- no signatory: rejected before the other inputs and outputs are read
      clear hSig hIn hOut
      rcases c with _ | _ <;> rcases locker with _ | _ <;> blaster
    · by_cases hs : s = bh
      · by_cases hsf : start < finish
        · -- the only case that reads the other inputs and outputs
          clear hSig
          repeat' (first
            | (simp only [List.length_cons, List.length_nil] at hIn hOut; exfalso; omega)
            | ((rcases ins with _ | ⟨i, ins⟩); rotate_left;
                by_cases hi : i.scriptHash = sh ∧
                  i.datum = datumData ⟨.PubKeyCredential bh, locker, [asset], start, finish, recovery⟩)
            | ((rcases outs with _ | ⟨o, outs⟩); rotate_left;
                by_cases ho : o.scriptHash = sh ∧
                  o.datum = datumData ⟨.PubKeyCredential bh, locker, [asset], start, finish, recovery⟩))
          all_goals (clear hIn hOut; rcases c with _ | _ <;> rcases locker with _ | _ <;> blaster)
        · -- `start ≥ end`: rejected before the other inputs and outputs are read
          clear hSig hIn hOut
          rcases c with _ | _ <;> rcases locker with _ | _ <;> blaster
      · -- signed by someone else: rejected before the other inputs and outputs are read
        clear hSig hIn hOut
        rcases c with _ | _ <;> rcases locker with _ | _ <;> blaster
    · simp only [List.length_cons] at hSig
      omega
  · -- infinite lower bound: rejected before the other inputs and outputs are read
    clear hSig hIn hOut
    rcases b with _ | _ <;> rcases locker with _ | _ <;> blaster

end Formal.Vesting.Linear.Claim
