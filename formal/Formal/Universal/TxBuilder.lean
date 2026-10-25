import CardanoLedgerApi

/-!
# Building script contexts

Validator-independent builders for the honest transactions in each validator's `Tx.lean`. Any
argument may be a variable, so that a shape can leave every leaf symbolic. `spend` adds the
bookkeeping the ledger model requires; inputs are taken in the order given, so the caller keeps
them sorted by reference.
-/

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V3

namespace Formal.Universal.TxBuilder

/-- `lovelace` ada and nothing else. -/
def ada (lovelace : Int) : Value :=
  [(.B "", .Map [(.B "", .I lovelace)])]

/-- `lovelace` ada and `qty` of one asset. -/
def adaAnd (lovelace : Int) (policy name : ByteString) (qty : Int) : Value :=
  [(.B "", .Map [(.B "", .I lovelace)]), (.B policy, .Map [(.B name, .I qty)])]

def keyAddress (key : ByteString) : Address := ⟨.PubKeyCredential key, none⟩

def scriptAddress (hash : ByteString) : Address := ⟨.ScriptCredential hash, none⟩

/-- An output to a key address, with no datum. -/
def toKey (key : ByteString) (value : Value) : TxOut :=
  ⟨keyAddress key, value, .NoOutputDatum, none⟩

/-- An output to a script address, with an inline datum. -/
def toScript (hash : ByteString) (value : Value) (datum : Data) : TxOut :=
  ⟨scriptAddress hash, value, .OutputDatum datum, none⟩

/-- A spend of `own`, with `others` as the remaining inputs, in that order. The datum passed to
    the script is `own`'s inline datum, if it has one; the redeemer is recorded for `own`. -/
def spend (own : TxInInfo) (others : List TxInInfo) (outputs : List TxOut)
    (signatories : List ByteString) (validFrom fee : Int) (txId : ByteString) (redeemer : Data) :
    ScriptContext :=
  let datum := match own.txInInfoResolved.txOutDatum with
    | .OutputDatum d => some d
    | _ => none
  { scriptContextTxInfo :=
      { txInfoInputs := own :: others
        txInfoReferenceInputs := []
        txInfoOutputs := outputs
        txInfoFee := fee
        txInfoMint := []
        txInfoTxCerts := []
        txInfoWdrl := []
        txInfoValidRange := IsData.toData (CardanoLedgerApi.V1.Time.after validFrom)
        txInfoSignatories := signatories
        txInfoRedeemers := [(.Spending own.txInInfoOutRef, redeemer)]
        txInfoData := []
        txInfoId := txId
        txInfoVotes := []
        txInfoProposalProcedures := []
        txInfoCurrentTreasuryAmount := IsData.toData (none : Option Int)
        txInfoTreasuryDonation := IsData.toData (none : Option Int) }
    scriptContextRedeemer := redeemer
    scriptContextScriptInfo := .SpendingScript own.txInInfoOutRef datum }

end Formal.Universal.TxBuilder
