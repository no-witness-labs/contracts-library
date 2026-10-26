-- The honest transactions for the checks in `Checks.lean`: for each action, a shape, that is a
-- transaction with a fixed structure whose leaves are the fields of a structure. Written once by
-- process_blueprint.py as a stub; it is never replaced, so edit it freely.
import CardanoLedgerApi
import Formal.Universal.TxBuilder
import Formal.Sale.Blueprint.Types

namespace Formal.Sale.Blueprint

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open CardanoLedgerApi.IsData.Class.IsData (toData)
open CardanoLedgerApi.V3 (ScriptContext)
open Formal.Universal.TxBuilder

/-- The policy of the item for sale. A literal: a symbolic policy stops Blaster inside
    `validScriptContext` (docs/Universal/DEAD_ENDS.md §17). -/
def itemPolicy : ByteString := "policyA"

def saleDatum (seller : ByteString) (price : Int) : Data :=
  toData ({ seller := seller, price := price } : Example.SaleDatum)

/-! ## buy: the listing and the buyer's ada in; the payment to the seller and the item to the
buyer out; no signatories, since anyone may buy. -/

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

def buy (p : BuyLeaves) : ScriptContext :=
  let listing := input p.prevTx 0
    (toScript p.script (adaAnd p.listingAda itemPolicy p.name p.qty) (saleDatum p.seller p.price))
  let buyerAda := input p.prevTx 1 (toKey p.buyer (ada p.buyerAda))
  let change := p.listingAda + p.buyerAda - p.paid - p.fee
  let payment := toKey p.seller (ada p.paid)
  let item := toKey p.buyer (adaAnd change itemPolicy p.name p.qty)
  Spend.context
    { own := listing
      others := [buyerAda]
      outputs := [payment, item]
      validFrom := p.now
      fee := p.fee
      txId := p.txId
      redeemer := toData Example.SaleRedeemer.Buy }

/-! ## cancel: the listing and the signer's ada in; everything back to the signer; one
signatory. -/

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

def cancel (p : CancelLeaves) : ScriptContext :=
  let listing := input p.prevTx 0
    (toScript p.script (adaAnd p.listingAda itemPolicy p.name p.qty) (saleDatum p.seller p.price))
  let feeInput := input p.prevTx 1 (toKey p.signer (ada p.feeInputAda))
  let change := p.listingAda + p.feeInputAda - p.fee
  let back := toKey p.signer (adaAnd change itemPolicy p.name p.qty)
  Spend.context
    { own := listing
      others := [feeInput]
      outputs := [back]
      signatories := [p.signer]
      validFrom := p.now
      fee := p.fee
      txId := p.txId
      redeemer := toData Example.SaleRedeemer.Cancel }

end Formal.Sale.Blueprint
