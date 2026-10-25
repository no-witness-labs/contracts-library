# Universal checks: the properties we keep

Two kinds of check are kept.
The **G checks** are proved by Blaster over every transaction, with no input from the validator's author.
The **H checks** are stated over a *shape*: a transaction for one action with a fixed structure and symbolic leaves, written by the validator's author.
Each H check states something about every member of the shape that the ledger model and the script accept, or about such a member with one thing changed.
H1 is always generated; the author selects the others with `--checks`.

## Where the checks live, and how to run them

Each validator has its own folder under `Formal/`, chosen when the checks are generated, for example `Formal/Vesting/Linear/Blueprint/` for linear vesting.
`scripts/process_blueprint.py` writes the folder from the blueprint (`plutus.json`):

| File | Written by | Contents |
|---|---|---|
| `Types.lean` | The generator, on every run | The validator's types and `IsData` instances, `args`, `program` (loaded with `#import_uplc`), `scriptHashHex`, `accepts` and `rejects`. |
| `General.lean` | The generator, on every run | The G checks. |
| `Honest.lean` | The generator, on every run | The H checks. |
| `Tx.lean` | The validator's author | The shapes, one per action. The generator writes it as a stub with `sorry` only when it does not exist, and never replaces it. |

The four files share the namespace given by the folder, for example `Formal.Vesting.Linear.Blueprint`.
Nothing imports them, so `lake build` does not check them; `just universal` does.
The helpers the checks use are in `Formal/Universal/Properties.lean`, in the namespace `Formal.Universal.Properties`.
Run from `formal/`:

```sh
just blueprint linear_vesting Formal/Vesting/Linear/Blueprint                      # from ../onchain/plutus.json
just blueprint linear_vesting Formal/Vesting/Linear/Blueprint path/to/plutus.json  # from another blueprint
just universal Formal/Vesting/Linear/Blueprint          # with Lean, Z3 and gawk on PATH
just universal-nix Formal/Vesting/Linear/Blueprint      # the same, inside `nix develop`
```

`just blueprint` first runs `just cbor <validator>`, which copies that validator's `compiledCode` from `plutus.json` to `Scripts/<module>.<validator>.cbor`, where `Types.lean` reads it.
Only the named validator's file is written, so the checks of one validator do not depend on any other validator's files.
`just universal` builds `Formal.Universal` and the folder's `Types.lean` and `Tx.lean`, then runs Lean on `General.lean` and on `Honest.lean`, each with a limit of 120 seconds.
Both generated check files set `set_option Elab.async false`, so Lean checks one proof at a time, in file order, and prints each result as soon as it is known.
In the brackets, `UP-0xx` is the number of the corresponding property in Jonathan's catalogue.

## Why the checks are split this way

A universal check is useful only if a pass means what the property says, for every transaction the check claims to cover.
A check that passes because it considered too few transactions is worse than no check, because it reads as assurance.

The earlier checks, in Jonathan's commits, covered the whole catalogue, but they finished only by narrowing the transactions:

- Every list held at most two items.
- In the fast mode, every sum type was fixed to its first constructor.

A pass then held only for those transactions.
Some checks could not fail at all: when no address has a staking part, "the continuing output keeps its staking credential" always holds.
Without the narrowing, the checks did not finish: Jonathan's notes record the full mode not finishing on vesting within 25 minutes.

The cause is how Blaster works, explained at the top of `DEAD_ENDS.md`.
Any property about what the script does after decoding its arguments, such as checking signatories or payments, requires the script's accepting run with every part of the transaction a variable, and that run does not finish.

So the checks are split by what can be proved:

- G1 and G2 are proved over every transaction, with nothing fixed, because the script rejects while it decodes its arguments, before it reads the transaction.
- Every other property is an H check, over a shape.
  With the structure of the transaction fixed and only its leaves symbolic, the script makes binary decisions on leaves, and the check finishes.

This is a good place to stop for the general checks.
G1 and G2 appear to be what Blaster can prove automatically for any validator, and extending the general checks further brings back the narrowing described above.
What remains is writing shapes for each contract, which adds coverage without changing the design.

Several ideas come from Jonathan's commits: the UP catalogue and its numbering, generating the checks from the blueprint, and testing by changing one thing in an accepted transaction.

## How to read a result

A pass is Blaster's message `✅ Valid`, followed by the warning `declaration uses 'blasterProven'` at the theorem's line.
`scripts/annotate-blaster-logs.awk` adds the theorem's name to that line, for example `[g1_mint]`.
A failure is an `error:` at the theorem's line, with `❌ Falsified`.
For a G check, the counterexample is an input that the script accepts although the check says it must be rejected, and it is a finding to review.
For an H check, a counterexample gives values of the shape's leaves; for H1, a failure means no member of the shape is both valid and accepted, and the shape is what to review first.

`accepts ledgerFuel ctx` means that the script, run on the script context `ctx`, ends with the unit value within `ledgerFuel` (1,000,000) steps of the CEK machine.
That limit is far above what any transaction the ledger accepts can use, so "not accepted within `ledgerFuel` steps" means "rejected" in practice.
`rejects ledgerFuel ctx` means that the script, run on `ctx`, reaches an error or ends with a value other than unit within `ledgerFuel` steps; running out of steps does not count as rejection.

## Tier 1: G checks, proved over every transaction

| Check | Property |
|---|---|
| G1 (UP-001) | A script context for a purpose that the validator has no handler for is rejected. |
| G2 (UP-005) | A redeemer that does not decode as the redeemer type declared in the blueprint is rejected. |

Each G check has the form `∀ …, ¬ accepts ledgerFuel (ctx)`.
Every part of the transaction that the statement does not name is a variable.

**G1** is generated once for each purpose without a handler: mint, withdraw, publish, vote, propose, or spend.
Each statement leaves the whole `TxInfo`, the redeemer and the purpose's own data as variables.
For example, `g1_mint` states that no mint is accepted, for any transaction, any redeemer and any policy.

**G2** is generated once for each way a redeemer can fail to decode, for each handler:

- `wrongForm_int`, `wrongForm_bytes`, `wrongForm_list`, `wrongForm_map`: the redeemer is an integer, a byte string, a list or a map instead of a constructor.
  For a redeemer type that is not a constructor type, the forms that differ from it are used instead.
- `unknownIndex2`, `unknownIndex3` (for a type with 2 constructors): the redeemer is a constructor whose index is not one of the type's.
- `<Constructor>_extraField`: the redeemer has the constructor's index and one field more than the constructor has.
- `<Constructor>_missingField`: the redeemer has the constructor's index and is missing its last field.
- `<Constructor>_wrongKind_<field>`: one field has the wrong kind of `Data`, for example a byte string where the type has an integer.

In a malformed redeemer that needs well-formed fields next to the malformed one, the integers, byte strings and credentials in those fields are variables, and their lists and maps are empty.
The lists are empty because a list of variable length makes Blaster follow one path per possible length.

**Measured result.**
On `linear_vesting`, G1 and G2 give 13 checks: 5 for G1, and 8 for G2 (4 forms, 2 unknown indices, and an extra field for each of `Claim` and `Cancel`).
All 13 were proved in one run of 34 seconds, including the time Lean takes to load.
They were proved again with `just universal Formal/Vesting/Linear/Blueprint`, in a run of `General.lean` that took 71 seconds on a different machine.
On `sale`, the same checks were proved.
On `stake`, G1 and the four `wrongForm` checks of G2 were proved earlier, in their earlier names (UP-001 and UP-005).

## Tier 2: H checks, over shapes

`Tx.lean` defines, for each action of each spend, mint and withdraw handler, a *shape*: `honest_<purpose>_<Action> : P → ScriptContext`, where `P` is a structure of the shape's leaves that the author defines.
For a validator with parameters, it also defines `honestParams`.
The shape fixes the structure of the transaction: the number of inputs, outputs and signatories, the kind of every address, datum and redeemer, and the assets in every value.
Every leaf, such as an amount, a time, a key or a hash, is a field of `P`, and so a variable in the checks.
The builders in `Formal/Universal/TxBuilder.lean` make it easy to build a transaction from leaves.

No predicate says which members are honest.
Each check quantifies over every value of the leaves, and uses "valid in the ledger model and accepted by the script" as its hypothesis, so Blaster itself finds which members the script accepts.
With the structure fixed, the script makes only binary decisions on leaves, such as a comparison of amounts or of keys, so the checks finish.

Each check below is generated for every shape it applies to.
H1 is always generated; the others only when named with `--checks`, for example `just blueprint linear_vesting Formal/Vesting/Linear/Blueprint H2,H11`, and are otherwise written into `Honest.lean` as comments.

A check on a change has the form `∀ p …, valid (shape p) → accepts (shape p) → [extra hypotheses] → valid (change) → verdict (change)`: the verdict is required only when the ledger would accept the changed transaction.
Beside it, a `_reach` check states `∃ p …, valid (shape p) ∧ accepts (shape p) ∧ [extra hypotheses] ∧ valid (change)`.
If the `_reach` check fails, no valid changed transaction exists, and the main check holds only because the ledger rejects the change; for an acceptance check, that makes its pass meaningless.

"Needs its continuations" means: with every output back to the script redirected to another key address, the member is rejected (`redirectContinuations`).
It keeps the continuation checks to members whose outputs back to the script matter; for example, a linear-vesting claim after the end time needs none.

| Check | Change, for every valid accepted member | Required verdict | Extra hypotheses |
|---|---|---|---|
| H1 (UP-000) | None: some member of the shape exists | Valid and accepted | |
| H2 (UP-002, UP-012) | One signatory removed, at each position | Rejected | |
| H3 (UP-004) | None: some member of the shape exists | Valid and rejected | |
| H4 | One signatory replaced by a key not in the list | Rejected | |
| H5 (UP-011) | The address of an output back to the script changed | Rejected | Needs its continuations |
| H7 (UP-014) | An output back to the script given another well-formed datum | Rejected | Needs its continuations |
| H8 (UP-006) | An output back to the script given a malformed datum, one variant per way of failing to decode | Rejected | Needs its continuations |
| H9 (UP-007) | The staking credential of an output back to the script changed | Rejected | Needs its continuations |
| H10 (UP-008) | A junk token, from a new input, added to an output back to the script | Rejected | Needs its continuations |
| **H11 (UP-010)** | **The spent input of any second valid accepted member added, its value pocketed, the outputs unchanged** | **One of the two script runs rejects, or one still accepts with the outputs back to the script redirected** | |
| H12 (UP-013) | The validity range made unbounded | Rejected | |
| H13 (UP-016) | One more token minted under the script's own policy (mint handlers) | Rejected | |
| H14 | The mint turned into a burn, or the other way round (mint handlers) | Rejected | |
| H15 | The redeemer changed to another action, in the redeemer map too | Rejected | |
| H16 (UP-015) | The outputs in reverse order | Accepted | |
| H17 | An unrelated input and an output of the same value added | Accepted | |
| H18 | The spent datum malformed, one variant per way of failing to decode | Rejected | |
| H19 | The spent input without a datum | Rejected, to review | |
| H23 | An unrelated input added before the script's own, and an output of the same value | Accepted | |
| H24 | An extra signatory, not already in the list | Accepted | |
| H25 | An unrelated token minted and sent to an unrelated output | Accepted | |
| H26 | A reference script on an output back to the script | Rejected, to review | Needs its continuations |

**H11, double satisfaction.**
The changed transaction is `p`'s, with the spent input of a second member `q` added under a new reference, `q`'s redeemer recorded for it, and an output sending `q`'s spent value to another key: one set of outputs for two script inputs.
Each script input runs the script separately, so the check considers the run for `p`'s input and the run for the new input.
Double satisfaction is both runs accepting while both rely on the outputs back to the script; the check requires that this never happens.
Because `q` is any member, it covers the same position spent twice (`q = p`) and two different positions.
A first form, which required `q` to need its continuations in `q`'s own transaction, was falsified by a legitimate case (`DEAD_ENDS.md` §18).

**Not generated.**
H6 and H21, "some amount of lovelace (H6) or tokens (H21) taken out of an output back to the script is rejected", are written as comments whatever `--checks` names, because their form is still to be decided (`DEAD_ENDS.md` §18).
H20 (UP-009) is not generated, because the ledger model treats a spent input with a hashed datum as invalid.

H1 also shows that the hypothesis of the checks on changes can hold, so they do not pass merely because no member is valid and accepted.
`validScriptContext` is the V3 model's `validScriptInfo` and `validTxInfo`.
For a spend, it requires, among other things:

- the redeemer map to contain the spend's redeemer for the spent input, with the spent input in the inputs, at a script address, with an inline datum equal to the datum passed to the script;
- inputs sorted by reference, signatories sorted, and the redeemer map sorted;
- every value with positive ada first, then currency symbols and token names sorted, with positive quantities;
- a fee greater than 0, and a non-empty validity range;
- a balanced transaction: the value in the inputs plus the mint equals the value in the outputs plus the fee.

The model does not check the length of hashes.

**Which leaves are symbolic.**
A leaf stays concrete only when a recorded limitation requires it.
Currently that is the currency symbol of a value: with a symbolic policy, Blaster stops inside `validScriptContext` with "Inductive datatype with instance parameters not supported" (`DEAD_ENDS.md` §17).

**Measured result.**
On `linear_vesting`, the `Claim` shape has 2 inputs (the vesting position and the signer's fee input), 2 outputs (the continuation and the payout) and 1 signatory, with 17 symbolic leaves: both keys, the token name, the total, the start, end and recovery times, the script hash, both transaction ids, the ada of both inputs, the ada and tokens kept, the fee, `now` and the signer.
The `Cancel` shape has 2 inputs, 1 output to the signer and 1 signatory, with 15 symbolic leaves.
H1 and H2 for both, 4 checks, were proved in a run of `Honest.lean` that took 29 seconds, including the time Lean takes to load.
H1 and H11 with its `_reach` check for both, 6 checks, were proved in a run that took 3 minutes 17 seconds.
The statements of all 180 checks generated with every check selected type-check; the other checks have not been run yet.

## Tier 3: not kept as general checks

These properties are not generated as G checks.
For each, the reason is given, and the H check that covers it, if any.

- **UP-000 (some transaction with this action is accepted) and UP-004 (some transaction with this action is rejected), stated over every transaction.**
  Blaster has to follow the script through its accepting run with every part of the transaction a variable.
  Each variable that the script inspects (a credential, an optional staking part, a datum, the length of a list) multiplies the number of paths.
  For UP-000 on `sale`, the run did not finish even with every list limited to at most 2 items and the datum and redeemer given their declared types.
  H1 covers UP-000 over a shape.
  Any H check that requires rejection will cover UP-004.
- **UP-002, UP-006, UP-007, UP-008, UP-010 and UP-013, stated as "every accepted transaction satisfies Q".**
  These require the same accepting run, for the same reason.
  H2 covers UP-002 over a shape; H3, H8, H9, H10, H11 and H12 will cover the others.
- **The datum checks over every transaction (a malformed datum is rejected; a spend without a datum is rejected).**
  On `linear_vesting`, the checks for a datum that is not a constructor were proved for the action `Cancel`.
  For the action `Claim`, the first of them had not finished when the run reached its 2-minute limit.
  For `Cancel`, the check for a datum with an unknown constructor index had not finished when the run reached its 2-minute limit.
  On `sale`, the checks for the action `Buy` did not finish.
  Whether they finish depends on where the compiled script first reads the datum, which cannot be known from the blueprint.
  H18 and H19 will cover them over a shape.
- **UP-009 (a spent input with a hashed datum can still be spent).**
  The ledger model in CardanoLedgerApi treats an input with a hashed datum whose datum is passed to the script as invalid, as Jonathan noted.
  It is not generated.
