-- The honest transactions for the H checks in `Honest.lean`: for each action, a shape, that is a
-- transaction with a fixed structure whose leaves are the fields of a structure. Written once by
-- process_blueprint.py as a stub; it is never replaced, so edit it freely.
import CardanoLedgerApi
import Formal.Universal.TxBuilder
import Formal.Sale.Blueprint.Types

namespace Formal.Sale.Blueprint

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open CardanoLedgerApi.IsData.Class (IsData)
open CardanoLedgerApi.V3 (ScriptContext TxInInfo)
open Formal.Universal.TxBuilder

/-- The listing's datum. The item's policy is the literal "policyA": a symbolic policy stops
    Blaster inside `validScriptContext` (docs/Universal/DEAD_ENDS.md §17). -/
def saleDatum (seller : ByteString) (price : Int) : Data :=
  IsData.toData ({ seller := seller, price := price } : Example.SaleDatum)

/-! ## Buy: 2 inputs (the listing, with ada and the item; the buyer's ada), 2 outputs (the payment
to the seller; the item to the buyer), no signatories: anyone may buy. -/

structure BuyLeaves where
  seller : ByteString
  price : Int
  name : ByteString
  qty : Int
  script : ByteString
  prevTx : ByteString
  txId : ByteString
  listingAda : Int
  buyerAda : Int
  paid : Int
  fee : Int
  now : Int
  buyer : ByteString

def honest_spend_Buy (p : BuyLeaves) : ScriptContext :=
  let own : TxInInfo :=
    ⟨⟨p.prevTx, 0⟩, toScript p.script (adaAnd p.listingAda "policyA" p.name p.qty) (saleDatum p.seller p.price)⟩
  let buyerInput : TxInInfo := ⟨⟨p.prevTx, 1⟩, toKey p.buyer (ada p.buyerAda)⟩
  spend own [buyerInput]
    [ toKey p.seller (ada p.paid),
      toKey p.buyer (adaAnd (p.listingAda + p.buyerAda - p.paid - p.fee) "policyA" p.name p.qty) ]
    [] p.now p.fee p.txId (IsData.toData Example.SaleRedeemer.Buy)

/-! ## Cancel: 2 inputs (the listing; the signer's fee input), 1 output (everything to the signer),
1 signatory. -/

structure CancelLeaves where
  seller : ByteString
  price : Int
  name : ByteString
  qty : Int
  script : ByteString
  prevTx : ByteString
  txId : ByteString
  listingAda : Int
  feeInputAda : Int
  fee : Int
  now : Int
  signer : ByteString

def honest_spend_Cancel (p : CancelLeaves) : ScriptContext :=
  let own : TxInInfo :=
    ⟨⟨p.prevTx, 0⟩, toScript p.script (adaAnd p.listingAda "policyA" p.name p.qty) (saleDatum p.seller p.price)⟩
  let feeInput : TxInInfo := ⟨⟨p.prevTx, 1⟩, toKey p.signer (ada p.feeInputAda)⟩
  spend own [feeInput]
    [ toKey p.signer (adaAnd (p.listingAda + p.feeInputAda - p.fee) "policyA" p.name p.qty) ]
    [p.signer] p.now p.fee p.txId (IsData.toData Example.SaleRedeemer.Cancel)

end Formal.Sale.Blueprint
