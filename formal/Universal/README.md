# Universal checks

A universal property is a security property that applies to any compiled validator, with nothing written by the validator's author. This folder holds a prototype. A generator reads a validator's blueprint (`plutus.json`) and writes the checks as Blaster theorems for that validator. It then runs them and prints a report, with a witness or counterexample for each verdict.

The author only compiles. The same checks ran on the two demo vaults in [`Demo/aiken/`](Demo/aiken/) and on the catalogue's own [`linear_vesting`](../../onchain/validators/linear_vesting.ak). The generated modules are committed with the compiled code written into each validator's `Base.lean`, so `lake build Universal.Demo.Linear_vesting` reproduces the vesting result (quick mode) without Python or Aiken, and a new build of the contract changes `Base.lean`, so lake rebuilds every check. Lean reports every failed check and every solver timeout as an error, so that build ends in errors for any contract with a HOLE or a REVIEW item; vesting has two REVIEW items (UP-011). The script turns those errors into the labels below.

This file is the short guide. The design notes, the prior art, why the shape is bounded, the review history, the limits and the candidate checks are in [`Notes.lean`](Notes.lean), so they build and ship with the modules; each generated module repeats the essentials in its header.

## Run it

From `formal/`, inside the Nix shell (`nix develop`):

```sh
python3 scripts/universal.py --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
python3 scripts/universal.py --blueprint ../onchain/plutus.json --quick linear_vesting
```

Full mode writes one module per check and per combination of the datum's constructors, so a vesting beneficiary is checked as a key and as a script in separate modules, with at most 16 modules per check (`--max-cases`); sums that do not fit stay open choices inside each module. `--quick` pins every sum type in the datum and redeemer to its first constructor instead: fewer modules, at the cost of the paths behind the other constructors. Leave it out for the run that counts. The modules sit under `Demo/<Validator>/` and build four at a time (`--jobs`), each with a time limit on the wall clock (`--timeout`, 600 seconds by default); a module that runs longer is stopped and reports UNDETERMINED. The exit code is 1 when a HOLE remains, 2 when a check has no verdict (UNDETERMINED, UNREACHED or UNKNOWN), 0 otherwise. The report for the buggy vault ends like this:

```text
HOLE      UP-001/mint      rejects undeclared purpose `mint`
          consequence: accepted a mint or burn under this script's hash; ...
          counterexample: cs = ("A"), rp = 0, ...
WAIVED    UP-002           action `spend` rejects a spend with no signatories
          waived: demo waiver: pretend this vault is permissionless by design
```

| Label | Meaning |
| --- | --- |
| PASS | The check holds within the generated shape (see Limits). For a sanity check, the witness Blaster found is printed. |
| HOLE | The check fails and almost no contract should fail it. The counterexample is printed. |
| REVIEW | The check fails but the behavior can be by design. The report lists every failing case, to confirm or to waive; a waiver covers the whole check. |
| WAIVED | A REVIEW or HOLE line that [`universal.json`](../universal.json) waives, with a reason, an owner and an expiry date if given. An expired waiver no longer applies, and `"state": "off"` switches a check off. |
| UNREACHED | No accepted spend exists for this action within the shape, so a "rejects" check for that action proved nothing. |
| UNDETERMINED | The check ran out of time, or the solver gave up. The report names the modules that were stopped. |
| UNKNOWN | Blaster gave no verdict for this check. Silence is never counted as a pass. |

## The candidates prototyped here

Every property below is a candidate, not an accepted entry: each one has its ticket (#22 to #37) and nothing is decided yet. This prototype covers six of them.

| Candidate | Statement | Severity |
| --- | --- | --- |
| UP-000, per action | Some realistic, ledger-valid spend with this redeemer is accepted. Otherwise funds are stuck, or the action needs a shape the generator lacks. | review |
| UP-001, per undeclared purpose | The script rejects every purpose its blueprint declares no handler for (mint, withdraw, publish, vote, propose), with that purpose's witness and redeemer entry present in the transaction. | hole |
| UP-002, per action | A ledger-valid spend with no signatories is rejected. | review |
| UP-004, per action | Some realistic, ledger-valid spend with this redeemer is rejected. Otherwise the action is always true. | hole |
| UP-005 | A ledger-valid spend with a malformed redeemer is rejected: any integer, and any constructor index the type lacks. Only when the blueprint types the redeemer. | hole |
| UP-011, per action | A spend accepted with its output back at the script, under any datum of the blueprint's shape, is rejected once that output moves to a key address or to a different script's address. | review |

UP-000 and UP-004 are stated backwards, as a universal claim that Blaster must falsify (`#blaster (solve-result: 1)`), the way the `cannot_unlock_nft` test in Input Output's (IOG) CardanoLedgerApiBlaster does. The falsifying witness is a working transaction, found by Blaster, not supplied by anyone.

## How a check is stated

The open values are the fields of one `Holes` structure per validator, and the transaction is composed from the small builders in [`Harness.lean`](Harness.lean): `optList`, `upTo2`, `scriptInput`, `outputWithDatum`, `payment`, `validity`, `tx`. Each check quantifies over one `h : Holes` and pins the fields it needs with hypotheses (`h.sig1 = false → ...`). This is the proof-harness pattern of Kani, with a bound on every list. IOG's own tests (`∀ input : SpendingInput`) also gather the open values in one structure, but leave the whole context open, with no bound; on vesting that did not finish (see Results).

The transaction is generic. Every list the shape covers holds up to two items, a Bool flag per item says whether it is present, and every value is open. Every sum type in the datum or the redeemer becomes a Bool-selected choice between its constructors, so a vesting beneficiary can be a key or a script. In every spend check, the continuing output carries a datum of the same shape with its own leaves and choices, so it may differ from the input's in any way the shape allows. A mint, when present, lands in the continuing output, so the balance can absorb it. Blaster picks all the flags and values.

On the spend checks, the ledger rules from CardanoLedgerApi (`validScriptContext`) are a hypothesis, so every witness and counterexample pays a fee and balances. The model does not enforce the ledger's minimum ada on an output, so a second hypothesis stands in for it, chosen by the kind of claim:

- A check that must hold for every transaction (UP-002, UP-005, UP-011) assumes only the ledger's floor, 689,600 lovelace on every input and output (4,310 lovelace per byte times the 160-byte overhead, CIP-55). Every real transaction meets it, so a PASS covers every amount the chain allows.
- A check whose answer is a witness (UP-000, UP-004) asks 1 ada of every amount, so the witness is not dust. That is close to the ledger, not exact: an output with a datum and tokens can need more than 1 ada, so a witness is a near-real transaction, not one guaranteed to land on chain.

The purpose checks are unconditional, and each purpose context carries the purpose's witness: the mint entry, the withdrawal, the certificate, the vote or the proposal, plus the matching redeemer entry.

The script is the blueprint's `compiledCode`, written into `Base.lean` and decoded with PlutusCoreBlaster's `singleCborEncodedScriptFromHexM`, and it runs through the CEK model with the shared predicates in [`Formal/Common.lean`](../Formal/Common.lean), one theorem per module.

## Results on 2026-10-26

Four modules in parallel, on the fork's pinned Blaster, PlutusCoreBlaster and CardanoLedgerApiBlaster:

| Validator | Modules | Result | Time |
| --- | --- | --- | --- |
| `vault` | 9 | 8 pass; UP-011 review: a vault pays out anywhere by design | 89 s for both vaults |
| `vault_buggy` | 9 | 6 holes: always-true `spend`, and all five undeclared purposes accepted; UP-002 waived; UP-011 review | |
| `linear_vesting`, quick mode | 15 | 12 pass; UP-011 review on Claim and on Cancel, both pay out by design | 4 min |
| `linear_vesting`, full mode | 180 | the same verdicts | 35 min |

`linear_vesting` is the compiled code from this repository's committed `onchain/plutus.json` (Aiken v1.1.22). The two demo vaults were compiled from `Demo/aiken/` with Aiken v1.1.19. The vaults have no sum types in their datum, so quick and full mode are the same for them.

In full mode on vesting, Claim is reachable only when the beneficiary is a key, and Cancel only when the locker is a key, because within the shape only a key can authorize. The report counts the other cases as unreached, for example `UP-002/Claim (8 of 16 cases pass, 8 unreached)`. A first version of the case split, which missed UP-011, took 3.7 hours.

Two of IOG's own patterns were tried and are not the default here. `#prep_uplc` (apply the script once to a symbolic context) finished in 15 seconds on the vault but not within 5 minutes on vesting; it stays behind `--prep`. A fully open context with no shape, as in IOG's `SellNFT` tests, did not finish the vesting sanity check within 5 minutes either. The bounded shape is what finishes.

## Limits, in one line

A PASS holds within the generated shape: no reference inputs, withdrawals, certificates, datum hashes or tokens on inputs, at most two of each list, exactly one item in each list inside a datum, and no entries in a map inside a datum. `Notes.lean` has the full list and what the review left open.
