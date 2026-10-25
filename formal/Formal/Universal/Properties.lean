import PlutusCore.UPLC
import CardanoLedgerApi

/-!
# Helpers for universal checks

Hand-written once; used by the generated files of each validator (`Types.lean`, `General.lean`
and `Honest.lean` in the folder given to `just blueprint`), which state the G checks and the H checks.

* G checks hold for every transaction: the builders `Every<Purpose>` leave the whole `TxInfo`, and
  the purpose's own data, as variables.
* H checks start from one accepted transaction written by the validator's author and change one
  thing in it; the helpers below make those changes.
-/

open PlutusCore.Data (Data)
open PlutusCore.ByteString (ByteString)
open PlutusCore.UPLC.Term (Program Term Const)
open PlutusCore.UPLC.CekMachine (State step initialState applyParams)
open CardanoLedgerApi.V3

namespace Formal.Universal.Properties

/-! ## Building script contexts -/

def mkCtx (txInfo : TxInfo) (red : Redeemer) (scInfo : ScriptInfo) : ScriptContext :=
  { scriptContextTxInfo := txInfo
    scriptContextRedeemer := red
    scriptContextScriptInfo := scInfo }

def keyAddr (h : PubKeyHash) : Address := ⟨.PubKeyCredential h, none⟩

/-! ## Running the script -/

/-- The step limit: far more than any transaction the ledger accepts can use. -/
abbrev ledgerFuel : Nat := 1000000

/-- `runSteps` without the conflation: `none` when the steps run out before `Halt` or `Error`. -/
def runFor : State → Nat → Option State
  | .Halt v, _ => some (.Halt v)
  | .Error, _ => some .Error
  | _, 0 => none
  | s, n + 1 => runFor (step default s) n

/-- The program, applied to `args`, fails within `fuel` steps: it reaches `Error`, or halts with a
    value other than `()`. Running out of steps is not a failure. -/
def rejectedWithin (p : Program) (args : List Term) (fuel : Nat) : Prop :=
  match p with
  | .Program _ body =>
      match runFor (initialState (applyParams body args)) fuel with
      | some .Error => True
      | some (.Halt v) => v ≠ .VCon Const.Unit
      | _ => False

/-! ## Every transaction, per purpose (G checks) -/

structure EverySpend where
  txInfo : TxInfo
  ref : TxOutRef
  datum : Option Datum

def EverySpend.ctx (t : EverySpend) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.SpendingScript t.ref t.datum)

/-- The same spend with the datum `d` passed to the script instead of `t.datum`. -/
def EverySpend.ctxDatum (t : EverySpend) (d : Option Datum) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.SpendingScript t.ref d)

structure EveryMint where
  txInfo : TxInfo
  policy : CurrencySymbol

def EveryMint.ctx (t : EveryMint) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.MintingScript t.policy)

structure EveryWithdraw where
  txInfo : TxInfo
  cred : Credential

def EveryWithdraw.ctx (t : EveryWithdraw) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.RewardingScript t.cred)

structure EveryPublish where
  txInfo : TxInfo
  idx : Int
  cert : TxCert

def EveryPublish.ctx (t : EveryPublish) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.CertifyingScript t.idx t.cert)

structure EveryVote where
  txInfo : TxInfo
  voter : Voter

def EveryVote.ctx (t : EveryVote) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.VotingScript t.voter)

structure EveryPropose where
  txInfo : TxInfo
  idx : Int
  proposal : ProposalProcedure

def EveryPropose.ctx (t : EveryPropose) (r : Data) : ScriptContext :=
  mkCtx t.txInfo r (.ProposingScript t.idx t.proposal)

/-! ## Changes to an honest transaction (H checks) -/

def inputsOf (h : ScriptContext) : List TxInInfo := h.scriptContextTxInfo.txInfoInputs
def outputsOf (h : ScriptContext) : List TxOut := h.scriptContextTxInfo.txInfoOutputs
def signatoriesOf (h : ScriptContext) : List PubKeyHash := h.scriptContextTxInfo.txInfoSignatories
def mintOf (h : ScriptContext) : MintValue := h.scriptContextTxInfo.txInfoMint

/-- `xs` with the item at `i` replaced by `f` of it (unchanged when `i` is out of range). -/
def modifyAt {α : Type} : List α → Nat → (α → α) → List α
  | [], _, _ => []
  | x :: xs, 0, f => f x :: xs
  | x :: xs, n + 1, f => x :: modifyAt xs n f

/-- The positions of the items satisfying `p`, counting from `n`. -/
def positionsFrom {α : Type} (p : α → Bool) : List α → Nat → List Nat
  | [], _ => []
  | x :: xs, n => (if p x then [n] else []) ++ positionsFrom p xs (n + 1)

def withSignatories (h : ScriptContext) (sigs : List PubKeyHash) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoSignatories := sigs } }

def withOutputs (h : ScriptContext) (outs : List TxOut) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoOutputs := outs } }

def withInputs (h : ScriptContext) (ins : List TxInInfo) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoInputs := ins } }

def withRange (h : ScriptContext) (r : Data) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoValidRange := r } }

def withMint (h : ScriptContext) (m : MintValue) : ScriptContext :=
  { h with scriptContextTxInfo := { h.scriptContextTxInfo with txInfoMint := m } }

def withRedeemer (h : ScriptContext) (r : Data) : ScriptContext :=
  { h with scriptContextRedeemer := r }

/-- `h` with the output at `i` replaced by `f` of it. -/
def changeOutput (h : ScriptContext) (i : Nat) (f : TxOut → TxOut) : ScriptContext :=
  withOutputs h (modifyAt h.scriptContextTxInfo.txInfoOutputs i f)

/-- The input being spent, if the context is a spend and the input is in the transaction. -/
def ownInput? (ctx : ScriptContext) : Option TxInInfo :=
  match ctx.scriptContextScriptInfo with
  | .SpendingScript ref _ => ctx.scriptContextTxInfo.txInfoInputs.find? (fun i => i.txInInfoOutRef == ref)
  | _ => none

/-- The positions of the outputs with the same payment credential as the input being spent. -/
def continuingPositions (ctx : ScriptContext) : List Nat :=
  match ownInput? ctx with
  | some i =>
      positionsFrom
        (fun o => o.txOutAddress.addressCredential == i.txInInfoResolved.txOutAddress.addressCredential)
        ctx.scriptContextTxInfo.txInfoOutputs 0
  | none => []

/-- `h` with a second input from the same output as the input being spent, under `ref`. -/
def duplicateOwnInput (h : ScriptContext) (ref : TxOutRef) : ScriptContext :=
  match ownInput? h with
  | some i => withInputs h (List.append h.scriptContextTxInfo.txInfoInputs [⟨ref, i.txInInfoResolved⟩])
  | none => h

/-- `h`, a spend, with its datum replaced by `d`: both the datum passed to the script and the inline
    datum on the input being spent. -/
def withSpendDatum (h : ScriptContext) (d : Datum) : ScriptContext :=
  match h.scriptContextScriptInfo with
  | .SpendingScript ref _ =>
      let ins := List.map (fun (i : TxInInfo) =>
        if i.txInInfoOutRef == ref then
          { i with txInInfoResolved := { i.txInInfoResolved with txOutDatum := .OutputDatum d } }
        else i) h.scriptContextTxInfo.txInfoInputs
      { withInputs h ins with scriptContextScriptInfo := .SpendingScript ref (some d) }
  | _ => h

/-- `h`, a spend, with no datum: none passed to the script, and none on the input being spent. -/
def withoutSpendDatum (h : ScriptContext) : ScriptContext :=
  match h.scriptContextScriptInfo with
  | .SpendingScript ref _ =>
      let ins := List.map (fun (i : TxInInfo) =>
        if i.txInInfoOutRef == ref then
          { i with txInInfoResolved := { i.txInInfoResolved with txOutDatum := .NoOutputDatum } }
        else i) h.scriptContextTxInfo.txInfoInputs
      { withInputs h ins with scriptContextScriptInfo := .SpendingScript ref none }
  | _ => h

/-- The value with 1 lovelace less. -/
def lowerLovelace (v : Value) : Value :=
  List.map (fun e => match e with
    | (.B b, .Map [(.B n, .I q)]) =>
        if b == "" && n == "" then (.B b, .Map [(.B n, .I (q - 1))]) else e
    | _ => e) v

/-- The value with one token of an unrelated policy added. -/
def withJunkToken (v : Value) : Value :=
  List.append v [(.B "6a756e6b", .Map [(.B "6a756e6b", .I 1)])]

/-- The mint with every quantity negated: a mint becomes a burn, and the other way round. -/
def negateMint (m : MintValue) : MintValue :=
  List.map (fun e => match e with
    | (p, .Map ts) => (p, .Map (List.map (fun t => match t with
        | (n, .I q) => (n, .I (-q))
        | _ => t) ts))
    | _ => e) m

/-- `h`, a mint, with one more token under its own policy. -/
def mintOneMore (h : ScriptContext) : ScriptContext :=
  match h.scriptContextScriptInfo with
  | .MintingScript pol =>
      withMint h (List.append h.scriptContextTxInfo.txInfoMint [(.B pol, .Map [(.B "65787472", .I 1)])])
  | _ => h

/-- An output unrelated to the script: 2 ada to a key address, no datum. -/
def unrelatedOutput : TxOut :=
  ⟨keyAddr ("756e72656c61746564" : ByteString), [(.B "", .Map [(.B "", .I 2000000)])], .NoOutputDatum, none⟩

/-- The validity range (−∞, +∞), as ledger `Data`. -/
def rangeAlways : Data :=
  .Constr 0 [.Constr 0 [.Constr 0 [], .Constr 1 []], .Constr 0 [.Constr 2 [], .Constr 1 []]]

end Formal.Universal.Properties
