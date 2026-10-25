-- The honest transactions for the H checks in `Honest.lean`: for each action, one transaction
-- that the ledger model and the script both accept. Written once by process_blueprint.py as
-- a stub; it is never replaced, so edit it freely.
import CardanoLedgerApi
import Formal.Vesting.Linear.Blueprint.Types

namespace Formal.Vesting.Linear.Blueprint

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V3 (Address ScriptContext TxInInfo TxOut TxOutRef Value)

/-! ## What both transactions share -/

def beneficiaryKey : ByteString := "beneficiary_key_hash_28bytes"
def lockerKey : ByteString := "locker_key_hash_28bytes_____"
def vestingScriptHash : ByteString := "linear_vesting_script_hash__"
def vestedPolicy : ByteString := "policyA"
def vestedName : ByteString := "assetA"

def vestingAddress : Address := ⟨.ScriptCredential vestingScriptHash, none⟩
def keyAddress (h : ByteString) : Address := ⟨.PubKeyCredential h, none⟩

/-- 100 tokens vesting linearly from time 1000 to 2000; the locker may recover them after 3000. -/
def honestDatum : Vesting.Types.VestingDatum :=
  { beneficiary := .PubKeyCredential beneficiaryKey
    locker := .PubKeyCredential lockerKey
    vesting := [{ policy := vestedPolicy, name := vestedName, total := 100 }]
    start_time := 1000
    end_time := 2000
    recovery_time := 3000 }

def adaOnly (lovelace : Int) : Value :=
  [(.B "", .Map [(.B "", .I lovelace)])]

def adaAndVested (lovelace quantity : Int) : Value :=
  [(.B "", .Map [(.B "", .I lovelace)]), (.B vestedPolicy, .Map [(.B vestedName, .I quantity)])]

/-- The output being spent: the vesting position, with 2 ada and all 100 tokens. -/
def vestingRef : TxOutRef := ⟨"previous_transaction_id_32bytes_", 0⟩
def vestingInput : TxInInfo :=
  ⟨vestingRef, ⟨vestingAddress, adaAndVested 2000000 100, .OutputDatum (IsData.toData honestDatum), none⟩⟩

/-- A spend of `vestingInput` at time `now`, signed by `signer`, whose ada for the fee comes from
    a second input of 5 ada at `signer`'s key address. The two inputs are sorted by reference. -/
def honestSpend (redeemer : Vesting.Types.VestingRedeemer) (now : Int) (signer : ByteString)
    (outputs : List TxOut) (fee : Int) : ScriptContext :=
  let feeInput : TxInInfo :=
    ⟨⟨"previous_transaction_id_32bytes_", 1⟩, ⟨keyAddress signer, adaOnly 5000000, .NoOutputDatum, none⟩⟩
  { scriptContextTxInfo :=
      { txInfoInputs := [vestingInput, feeInput]
        txInfoReferenceInputs := []
        txInfoOutputs := outputs
        txInfoFee := fee
        txInfoMint := []
        txInfoTxCerts := []
        txInfoWdrl := []
        txInfoValidRange := IsData.toData (CardanoLedgerApi.V1.Time.after now)
        txInfoSignatories := [signer]
        txInfoRedeemers := [(.Spending vestingRef, IsData.toData redeemer)]
        txInfoData := []
        txInfoId := "honest_transaction_id_32bytes___"
        txInfoVotes := []
        txInfoProposalProcedures := []
        txInfoCurrentTreasuryAmount := IsData.toData (none : Option Int)
        txInfoTreasuryDonation := IsData.toData (none : Option Int) }
    scriptContextRedeemer := IsData.toData redeemer
    scriptContextScriptInfo := .SpendingScript vestingRef (some (IsData.toData honestDatum)) }

/-! ## The honest transactions -/

/-- A partial claim at time 1500, when 50 of the 100 tokens have vested. The beneficiary signs,
    takes the 50 vested tokens, and sends exactly the required 50 back to the script with the
    same datum. Inputs: 7 ada and 100 tokens. Outputs: 6.8 ada and 100 tokens. Fee: 0.2 ada. -/
def honest_spend_Claim : ScriptContext :=
  honestSpend .Claim 1500 beneficiaryKey
    [ ⟨vestingAddress, adaAndVested 2000000 50, .OutputDatum (IsData.toData honestDatum), none⟩,
      ⟨keyAddress beneficiaryKey, adaAndVested 4800000 50, .NoOutputDatum, none⟩ ]
    200000

/-- A cancel at time 3500, after the recovery time of 3000. The locker signs and takes
    everything, with no output back to the script. Inputs: 7 ada and 100 tokens. Outputs:
    6.8 ada and 100 tokens. Fee: 0.2 ada. -/
def honest_spend_Cancel : ScriptContext :=
  honestSpend .Cancel 3500 lockerKey
    [ ⟨keyAddress lockerKey, adaAndVested 6800000 100, .NoOutputDatum, none⟩ ]
    200000

end Formal.Vesting.Linear.Blueprint
