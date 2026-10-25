-- Supporting definitions copied unchanged from PR #44 at 99a5734f0e036b6abfb4c3f121a298e35fa2eff6.
import Formal.Universal.Properties

open CardanoLedgerApi.V3

namespace Formal.Universal.Properties

def signatoriesOf (h : ScriptContext) : List PubKeyHash := h.scriptContextTxInfo.txInfoSignatories

def withSignatories (h : ScriptContext) (sigs : List PubKeyHash) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoSignatories := sigs } }

end Formal.Universal.Properties
