# Universal checks: the properties we keep

Two kinds of check are kept.
The **G checks** are proved by Blaster over every transaction, with no input from the validator's author.
The **H checks** are stated on an *honest transaction*: a transaction for one action that the ledger model and the script both accept, written by the validator's author.
Each H check states something about the honest transaction, or about the honest transaction with one thing changed.
For now, only H0 and H1 are generated; the other H checks are added back one at a time once these have been run on more validators.

## Where the checks live, and how to run them

Each validator has its own folder under `Formal/`, chosen when the checks are generated, for example `Formal/Vesting/Linear/Blueprint/` for linear vesting.
`scripts/process_blueprint.py` writes the folder from the blueprint (`plutus.json`):

| File | Written by | Contents |
|---|---|---|
| `Types.lean` | The generator, on every run | The validator's types and `IsData` instances, `args`, `program` (loaded with `#import_uplc`), `scriptHashHex`, `accepts` and `rejects`. |
| `General.lean` | The generator, on every run | The G checks. |
| `Honest.lean` | The generator, on every run | The H checks. |
| `Tx.lean` | The validator's author | The honest transactions, one per action. The generator writes it as a stub with `sorry` only when it does not exist, and never replaces it. |

The four files share the namespace given by the folder, for example `Formal.Vesting.Linear.Blueprint`.
Nothing imports them, so `lake build` does not check them; `just universal` does.
The helpers the checks use are in `Formal/Universal/Properties.lean`, in the namespace `Formal.Universal.Properties`.
Run from `formal/`:

```sh
just blueprint linear_vesting Formal/Vesting/Linear/Blueprint                      # from ../onchain/plutus.json
just blueprint linear_vesting Formal/Vesting/Linear/Blueprint path/to/plutus.json  # from another blueprint
just universal Formal/Vesting/Linear/Blueprint          # inside `nix develop`
just universal-local Formal/Vesting/Linear/Blueprint    # with Lean, Z3 and gawk already on PATH
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
- Every other property is an H check, on an honest transaction.
  With a concrete transaction, the script follows a single path.
  Because the transaction is one the ledger model and the script accept (H0 and H1), a pass cannot hold for the wrong reason.

This is a good place to stop for the general checks.
G1 and G2 appear to be what Blaster can prove automatically for any validator, and extending the general checks further brings back the narrowing described above.
What remains is writing honest transactions for each contract, which adds coverage without changing the design.

Several ideas come from Jonathan's commits: the UP catalogue and its numbering, generating the checks from the blueprint, and testing by changing one thing in an accepted transaction.

## How to read a result

A pass is Blaster's message `✅ Valid`, followed by the warning `declaration uses 'blasterProven'` at the theorem's line.
`scripts/annotate-blaster-logs.awk` adds the theorem's name to that line, for example `[g1_mint]`.
A failure is an `error:` at the theorem's line, with `❌ Falsified`.
For a G check, the counterexample is an input that the script accepts although the check says it must be rejected, and it is a finding to review.
For H0 or H1, a failure means the honest transaction in `Tx.lean` is not valid in the ledger model, or not accepted by the script; the transaction is what to review first.

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
They were proved again with `just universal-local Formal/Vesting/Linear/Blueprint`, in a run of `General.lean` that took 71 seconds on a different machine.
On `sale`, the same checks were proved.
On `stake`, G1 and the four `wrongForm` checks of G2 were proved earlier, in their earlier names (UP-001 and UP-005).

## Tier 2: H checks, on honest transactions

`Tx.lean` defines, for each action of each spend, mint and withdraw handler, `honest_<purpose>_<Action> : ScriptContext`.
For a validator with parameters, it also defines `honestParams`.

The honest transaction must be concrete: every list, every constructor and every leaf has a fixed value.
With a concrete transaction, the script follows a single path, which is why the H checks finish.

| Check | Statement | Required result |
|---|---|---|
| H0 | `validScriptContext honest = true` | The honest transaction is valid in the V3 ledger model. |
| H1 (UP-000) | `accepts ledgerFuel honest` | The script accepts the honest transaction. |

Together, H0 and H1 state UP-000 for a transaction the ledger accepts: some valid transaction with this action is accepted.
`validScriptContext` is the V3 model's `validScriptInfo` and `validTxInfo`.
For a spend, it requires, among other things:

- the redeemer map to contain the spend's redeemer for the spent input, with the spent input in the inputs, at a script address, with an inline datum equal to the datum passed to the script;
- inputs sorted by reference, signatories sorted, and the redeemer map sorted;
- every value with positive ada first, then currency symbols and token names sorted, with positive quantities;
- a fee greater than 0, and a non-empty validity range;
- a balanced transaction: the value in the inputs plus the mint equals the value in the outputs plus the fee.

The model does not check the length of hashes.

**Measured result.**
On `linear_vesting`, H0 and H1 give 4 checks, for `Claim` and `Cancel`.
All 4 were proved in a run of `Honest.lean` that took 11 seconds, including the time Lean takes to load.
Changing the honest transactions confirmed that the checks can fail: with a fee of 0, `h0_spend_Claim` was falsified, and with 49 tokens instead of the required 50 in the continuation, `h1_spend_Claim` was falsified.

### H checks to add back

These were generated before, with `by sorry`, and are not generated now.
They will be added back one at a time.
The change helpers they use are still in `Properties.lean`.

| Check | Change made to the honest transaction | Required verdict |
|---|---|---|
| H2 (UP-002) | Every signatory removed. | Rejected. |
| H3 (UP-012) | One signatory removed, for each signatory. | Rejected. |
| H4 | One signatory replaced by another key. | Rejected. |
| H5 (UP-011) | A protected output sent to another address. | Rejected. |
| H6 | 1 lovelace less in a protected output. | Rejected. |
| H7 (UP-014) | A protected output given another datum. | Rejected. |
| H8 (UP-006) | An output back to the script given a malformed datum. | Rejected. |
| H9 (UP-007) | An output back to the script given another staking credential. | Rejected. |
| H10 (UP-008) | A junk token added to an output back to the script. | Rejected. |
| H11 (UP-010) | A second input from the same script output added. | Rejected. |
| H12 (UP-013) | The validity range made unbounded. | Rejected. |
| H13 (UP-016) | One more token minted under the script's own policy. | Rejected. |
| H14 | The mint turned into a burn, or the other way round. | Rejected. |
| H15 | The redeemer changed to another action. | Rejected. |
| H16 (UP-015) | The outputs put in reverse order. | Accepted. |
| H17 | An unrelated output added (2 ada to a key address). | Accepted. |
| H18 | The spent input's datum replaced by a malformed one. | Rejected. |
| H19 | The spent input's datum removed. | Rejected. |

Points to settle when they are added back:

- Several changes make the transaction invalid in the ledger model; for example, H6 unbalances the ada.
  Each change helper should then also make the adjustment that keeps the transaction valid, such as adding the removed lovelace to the fee.
- H5 to H7 need the positions of the outputs the script must protect, which `Tx.lean` will then define as `honest_<purpose>_<Action>_protected`.
- H11 should require rejection only when the honest transaction has an output back to the script; cancelling two positions in one transaction is legitimate.

## Tier 3: not kept as general checks

These properties are not generated as G checks.
For each, the reason is given, and the H check that covers it, if any.

- **UP-000 (some transaction with this action is accepted) and UP-004 (some transaction with this action is rejected), stated over every transaction.**
  Blaster has to follow the script through its accepting run with every part of the transaction a variable.
  Each variable that the script inspects (a credential, an optional staking part, a datum, the length of a list) multiplies the number of paths.
  For UP-000 on `sale`, the run did not finish even with every list limited to at most 2 items and the datum and redeemer given their declared types.
  H0 and H1 cover UP-000 on an honest transaction.
  Any H check that requires rejection will cover UP-004.
- **UP-002, UP-006, UP-007, UP-008, UP-010 and UP-013, stated as "every accepted transaction satisfies Q".**
  These require the same accepting run, for the same reason.
  H2, H3, H8, H9, H10, H11 and H12 will cover them on an honest transaction.
- **The datum checks over every transaction (a malformed datum is rejected; a spend without a datum is rejected).**
  On `linear_vesting`, the checks for a datum that is not a constructor were proved for the action `Cancel`.
  For the action `Claim`, the first of them had not finished when the run reached its 2-minute limit.
  For `Cancel`, the check for a datum with an unknown constructor index had not finished when the run reached its 2-minute limit.
  On `sale`, the checks for the action `Buy` did not finish.
  Whether they finish depends on where the compiled script first reads the datum, which cannot be known from the blueprint.
  H18 and H19 will cover them on an honest transaction.
- **UP-009 (a spent input with a hashed datum can still be spent).**
  The ledger model in CardanoLedgerApi treats an input with a hashed datum whose datum is passed to the script as invalid, as Jonathan noted.
  It is not generated.
