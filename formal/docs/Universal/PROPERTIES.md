# Universal checks

A universal check is a property that any validator should have, checked on the compiled code with Blaster.
The checks are generated from the validator's blueprint (`plutus.json`).
The only input from the validator's author is `Tx.lean`, one honest transaction per action, called a *shape*.

Checks are called by name, such as `doubleSatisfaction`.
The numbers in this document, such as 9.1, only give the order; they are not used anywhere else.

## The checks

The checks are in sections, in the order of the parts of a transaction.
In each section, the checks that must reject come first, then the checks that must still accept.

"Over" says what a check quantifies over:

- **every tx**: every transaction of the purpose; everything not named in the statement is a variable.
- **shapes**: every value of the leaves of each shape in `Tx.lean`.

"Applies to" says which shapes a check is generated for, or when it says something:

- **continuations**: the check concerns transactions that need their outputs back to the script, meaning that with those outputs sent to another key, the transaction is rejected.
  For a shape without outputs back to the script, the check does not apply.
- **signatories**: the shape has at least one signatory.

"Former" is the check's earlier ID, used in `DEAD_ENDS.md` and older notes, where the `_applies` checks are called `_reach`.
"Catalogue" is the matching entry in Jonathan's catalogue of universal properties.

| No. | Name | Over | Change to an honest transaction | Expected | Applies to | Catalogue | Former |
|---|---|---|---|---|---|---|---|
| | **1. Sanity** | | | | | | |
| 1.1 | `someAccepted` | shapes | none | some transaction of the shape is valid and accepted | every shape | UP-000 | H1 |
| 1.2 | `someRejected` | shapes | none | some valid transaction of the shape is rejected | every shape | UP-004 | H3 |
| | **2. Purpose and arguments** | | | | | | |
| 2.1 | `otherPurpose` | every tx | a purpose the validator has no handler for | reject | each purpose without a handler | UP-001 | G1 |
| 2.2 | `malformedRedeemer` | every tx | a redeemer that does not decode as its declared type | reject | each handler | UP-005 | G2 |
| 2.3 | `otherRedeemer` | shapes | the redeemer changed to another action | reject | each other action | | H15 |
| 2.4 | `spendDatumTag` | shapes | the spent datum given an unknown constructor index, fields kept | reject | spends with a constructor datum | | H18 |
| 2.5 | `noSpendDatum` | shapes | the spent input without a datum | reject (review) | spends | | H19 |
| | **3. Signatories** | | | | | | |
| 3.1 | `dropSigner` | shapes | the first signatory removed | reject | signatories | UP-002, UP-012 | H2 |
| 3.2 | `wrongSigner` | shapes | the first signatory replaced by a key not in the list | reject | signatories | | H4 |
| 3.3 | `extraSigner` | shapes | a signatory not in the list added first | accept | every shape | | H24 |
| | **4. Inputs** | | | | | | |
| 4.1 | `unrelatedInput` | shapes | an unrelated input added before the script's own, with an output of the same value | accept | every shape | | H23 |
| | **5. Outputs** | | | | | | |
| 5.1 | `reverseOutputs` | shapes | the outputs in reverse order | accept | every shape | UP-015 | H16 |
| 5.2 | `rotateOutputs` | shapes | the first output moved to the end | accept | every shape | UP-015 | H27 |
| 5.3 | `unrelatedOutput` | shapes | an unrelated input and an output of the same value added | accept | every shape | | H17 |
| | **6. Outputs back to the script** | | | | | | |
| 6.1 | `continuationElsewhere` | shapes | the first output back to the script given another payment credential | reject | continuations | UP-011 | H5 |
| 6.2 | `continuationStake` | shapes | the first output back to the script given another staking credential | reject | continuations | UP-007 | H9 |
| 6.3 | `continuationOtherDatum` | shapes | the first output back to the script given another well-formed datum | reject | continuations, constructor datum | UP-014 | H7 |
| 6.4 | `continuationDatumTag` | shapes | that output's datum given an unknown constructor index, fields kept | reject | continuations, constructor datum | UP-006 | H8 |
| 6.5 | `junkToken` | shapes | a junk token, from a new input, appended to that output | reject | continuations | UP-008 | H10 |
| 6.6 | `continuationRefScript` | shapes | a reference script put on that output | reject (review) | continuations | | H26 |
| | **7. Mint** | | | | | | |
| 7.1 | `extraMint` | shapes | one more token minted under the script's own policy | reject | mints | UP-016 | H13 |
| 7.2 | `mintAsBurn` | shapes | the mint turned into a burn, or the other way round | reject | mints | | H14 |
| 7.3 | `unrelatedMint` | shapes | an unrelated token minted and sent to an unrelated output | accept | every shape | | H25 |
| | **8. Validity range** | | | | | | |
| 8.1 | `unboundedRange` | shapes | the validity range made unbounded | reject | every shape | UP-013 | H12 |
| | **9. Several script inputs** | | | | | | |
| 9.1 | **`doubleSatisfaction`** | shapes | the input of a second honest transaction of the same shape added, its value sent to another key, the outputs unchanged | the two script runs do not both accept while both relying on the outputs | spends | UP-010 | H11 |

Not generated:

- `continuationLovelace` and `continuationTokens` (former H6 and H21): some lovelace, or some tokens, taken out of an output back to the script is rejected.
  Their form is still to be decided (`DEAD_ENDS.md` §18).
- UP-009 (a spent input with a hashed datum can still be spent): the ledger model treats such an input as invalid.

## Running

Run from `formal/`, with the validator's recipe in the `justfile` (`vesting` for `linear_vesting`):

```sh
just vesting doubleSatisfaction                      # one check, with someAccepted
just vesting doubleSatisfaction --counterexamples    # the same, printing each counterexample
just vesting doubleSatisfaction --from-log           # summarise the last run's log without running Lean
```

One run is one check over every shape it applies to, with `someAccepted`, stopped after 5 minutes.
The recipe calls `scripts/universal.py`, which:

1. runs `aiken build` in the blueprint's folder, and fails if the validator is not in the blueprint, listing the validators that are;
2. copies the validator's `compiledCode` to `Scripts/<module>.<validator>.cbor`, where `Types.lean` reads it;
3. regenerates `Types.lean` and `Checks.lean` with `scripts/process_blueprint.py`; when `Tx.lean` did not exist, it writes a skeleton and stops;
4. builds `Formal.Universal` and the folder's `Types.lean` and `Tx.lean`;
5. runs Lean on `Checks.lean`, showing its output and saving it to `logs/<folder below Formal>/<check>.log`, for example `logs/Vesting/Linear/doubleSatisfaction.log`;
6. prints one line per check and shape, by section.

The files of a validator's `Blueprint/` folder:

| File | Written by | Contents |
|---|---|---|
| `Types.lean` | the generator, on every run | the validator's types and `IsData` instances, `program` (loaded with `#import_uplc`), `scriptHashHex`, `accepts` and `rejects` |
| `Tx.lean` | the validator's author | the shapes, one per action; written as a skeleton only when it does not exist, never replaced |
| `Checks.lean` | the generator, on every run | the selected check and `someAccepted`, in the order of the table; the other checks are listed in its header |

Nothing imports them, so `lake build` does not check them.
The helpers the checks use are in `Formal/Universal/Properties.lean`, and the builders for shapes in `Formal/Universal/TxBuilder.lean`.

## Reading a result

Each check gets one line per shape:

| Reading | Meaning |
|---|---|
| holds | proved, and its `_applies` check proved |
| does not apply | proved, but no valid changed transaction of that kind exists, so the check says nothing; for example `dropSigner` on a shape without signatories |
| FAILS | Blaster found a counterexample: values of the shape's leaves for which the check is false |
| no result | nothing was reported, usually because the 5-minute limit came first |
| error | Lean reported another error at the check |

A FAILS is not always a bug.
For a check that must reject, it is an accepted transaction that the check expected to be rejected: either a finding, or a case the validator allows on purpose.
For a check that must still accept, the validator is stricter than the check expects.
For `someAccepted`, no transaction of the shape is valid and accepted, and the shape is the first thing to review.

**`_applies`.**
A check on a change requires its verdict only when the changed transaction is valid in the ledger model.
Beside it, a check named `<name>_<shape>_applies` states that some honest transaction gives a valid changed transaction.
When it fails, the main check holds only because no such transaction exists, and the summary says "does not apply".

**Accepts and rejects.**
`accepts ledgerFuel ctx` means that the script, run on the script context `ctx`, ends with the unit value within `ledgerFuel` (1,000,000) steps of the CEK machine.
That limit is far above what any transaction the ledger accepts can use.
`rejects ledgerFuel ctx` means that the script reaches an error or ends with a value other than unit within `ledgerFuel` steps; running out of steps does not count as rejection.

## Writing shapes

`Tx.lean` defines, for each action of each spend, mint and withdraw handler, a shape: a function from a structure of leaves to a transaction, named after the action, for example `buy : BuyLeaves → ScriptContext`.
For a validator with parameters, it also defines `honestParams`.
The shape fixes the structure of the transaction: the number of inputs, outputs and signatories, the kind of every address, datum and redeemer, and the assets in every value.
Every amount, time, key or hash is a leaf, and so a variable in the checks.
No predicate says which transactions are honest: every check uses "valid in the ledger model and accepted by the script" as its hypothesis, so Blaster finds which values the script accepts.

A spend is written with `Spend.context { own, others, outputs, signatories, validFrom, fee, txId, redeemer }`, and every input and output named with `let`.
The generated skeleton has this form, with `sorry` where the author fills in the transaction.

Rules for shapes:

- **Signatories as independent leaves**, such as `[p.s1, p.s2]`, rather than `[p.owner, p.cosigner]`.
  The ledger sorts signatories, and the checks change the first signatory to stand for any one; with independent leaves, every assignment of roles to positions is covered.
- **Currency symbols as literals**, such as a constant `itemPolicy : ByteString := "policyA"`.
  With a symbolic policy, Blaster stops inside `validScriptContext` with "Inductive datatype with instance parameters not supported" (`DEAD_ENDS.md` §17).
  Every other leaf stays symbolic.
- **Inputs sorted by reference**, since the ledger model requires it; `input tx 0`, `input tx 1` with the same transaction id are sorted.

The ledger model, `validScriptContext`, requires among other things: the redeemer map to hold the spend's redeemer for the spent input; inputs, signatories and the redeemer map sorted; every value with positive ada first, then sorted assets with positive quantities; a fee greater than 0 and a non-empty validity range; and a balanced transaction.
It does not check the length of hashes.

## Design notes

**Why two kinds of check.**
A check is useful only if a pass means what the property says for every transaction it claims to cover.
The earlier checks, in Jonathan's commits, covered the whole catalogue, but finished only by narrowing the transactions: lists of at most two items and, in the fast mode, every sum type fixed to its first constructor.
Without the narrowing, they did not finish.
The cause is how Blaster works (`DEAD_ENDS.md`, top): a property about what the script does after decoding its arguments needs the script's accepting run with every part of the transaction a variable, and that run does not finish.
`otherPurpose` and `malformedRedeemer` are proved over every transaction because the script rejects while decoding its arguments, before it reads the transaction.
Every other check is over shapes: with the structure fixed and only the leaves symbolic, the script makes binary decisions on leaves, and the check finishes.

**The first signatory, the first output back to the script.**
No check uses a symbolic position in a list, because Blaster would follow every value the position could take (`DEAD_ENDS.md` §19).
Checks act on the first signatory, or the first output back to the script, instead.
That stands for any one of them because the order of outputs should not matter to a validator, which `reverseOutputs` and `rotateOutputs` check, and because signatories are independent leaves.
Conditions are Boolean tests, such as `contains k = false`, rather than membership (`∉`) or other inductive propositions, which Blaster handles poorly.

**doubleSatisfaction.**
The changed transaction is `p`'s, with the spent input of a second honest transaction `q` added under a new reference, `q`'s redeemer recorded for it, and an output sending that input's value to another key: one set of outputs for two script inputs.
Each script input runs the script separately.
Double satisfaction is both runs accepting while both rely on the outputs, and the check requires that this never happens.
A run relies on the outputs when it rejects with every output sent to another key (`redirectOutputs`).
Because `q` is any honest transaction of the shape, the check covers the same position spent twice and two different positions.
It covers only a second input of the same shape.
A first form, which required `q` to need its outputs back to the script, was falsified by a legitimate case (`DEAD_ENDS.md` §18).
A second form redirected only the outputs back to the script, and so passed on a sale that pays the seller's key.

## Results so far

| Check | linear vesting: claim | linear vesting: cancel | sale: buy | sale: cancel |
|---|---|---|---|---|
| `someAccepted` | holds | holds | holds | holds |
| `someRejected` | holds | holds | holds | holds |
| `otherPurpose` | holds | | holds | |
| `malformedRedeemer` | holds | | holds | |
| `otherRedeemer` | FAILS, legitimate: the beneficiary may be the locker | FAILS, legitimate | holds | FAILS, legitimate: a seller who pays themselves the price also satisfies buy |
| `spendDatumTag` | FAILS in an earlier form, to review | FAILS in an earlier form, to review | FAILS, to review | FAILS, to review |
| `noSpendDatum` | holds | holds | holds | holds |
| `dropSigner` | holds | holds | does not apply | holds |
| `wrongSigner` | holds | holds | does not apply | holds |
| `extraSigner` | holds | holds | holds | holds |
| `unrelatedInput` | holds | holds | holds | holds |
| `reverseOutputs` | holds | holds | holds | holds |
| `rotateOutputs` | holds | holds | holds | holds |
| `unrelatedOutput` | holds | holds | holds | holds |
| `continuationElsewhere` | holds | does not apply | does not apply | does not apply |
| `continuationStake` | **FAILS: the staking credential is not checked** | does not apply | does not apply | does not apply |
| `continuationOtherDatum` | holds | does not apply | does not apply | does not apply |
| `continuationDatumTag` | not run | does not apply | does not apply | does not apply |
| `junkToken` | **FAILS: extra tokens are accepted** | does not apply | does not apply | does not apply |
| `continuationRefScript` | FAILS, to review | does not apply | does not apply | does not apply |
| `unrelatedMint` | holds | holds | holds | holds |
| `unboundedRange` | holds | holds | FAILS, legitimate: the sale ignores time | FAILS, legitimate |
| `doubleSatisfaction` | holds | holds | **FAILS: one output pays for two listings** | holds |

These were run under the former IDs, before the checks were renamed; the statements are unchanged, apart from the new `doubleSatisfaction` form.
The G checks (`otherPurpose`, `malformedRedeemer`) on linear vesting gave 13 checks, proved in 34 to 71 seconds depending on the machine.
In the `doubleSatisfaction` counterexample on the sale, the second listing's seller is the first buyer, and the first buyer's own output, with the item and 1 lovelace, is enough to pay the second listing's price.
Blaster picked negative prices; a price up to that output's lovelace would likely work too.

## Not kept as checks over every transaction

- **UP-000 and UP-004 (some transaction of an action is accepted, or rejected).**
  Over every transaction, the accepting run does not finish: on `sale`, UP-000 did not finish even with every list limited to 2 items.
  `someAccepted` and `someRejected` cover them over shapes.
- **UP-002, UP-006, UP-007, UP-008, UP-010 and UP-013, stated as "every accepted transaction satisfies Q".**
  These need the same accepting run; the checks over shapes in the table cover them.
- **Datum checks over every transaction (a malformed datum, no datum).**
  Whether they finish depends on where the compiled script first reads the datum, which the blueprint does not say; on `linear_vesting` and `sale` some did not finish within 2 minutes.
  `spendDatumTag` and `noSpendDatum` cover them over shapes.
