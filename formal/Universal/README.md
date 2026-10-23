# Universal checks

A universal property is a security property that applies to any compiled validator, with nothing written by the validator's author. This folder holds a prototype. A generator reads a validator's blueprint (`plutus.json`) and writes the checks as Blaster theorems for that validator. It then runs them and prints a report, with a witness or counterexample for each verdict.

The author only compiles. The same checks ran on the two demo vaults in [`Demo/aiken/`](Demo/aiken/) and on the catalogue's own [`linear_vesting`](../../onchain/validators/linear_vesting.ak). The generated modules and the compiled code are committed, so `lake build Universal.Demo.Linear_vesting` reproduces the vesting result (quick mode) without Python or Aiken. Lean reports every failed check as an error, so that build ends in errors for any contract with a HOLE or a REVIEW item; vesting has two REVIEW items (UP-011). The script turns those errors into the labels below.

This file is the short guide. The design notes, the prior art, why the shape is bounded, the review history, the limits and the candidate checks are in [`Notes.lean`](Notes.lean), so they build and ship with the modules; each generated module repeats the essentials in its header.

## Run it

From `formal/`, inside the Nix shell (`nix develop`):

```sh
python3 scripts/universal.py --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
python3 scripts/universal.py --blueprint ../onchain/plutus.json --quick linear_vesting
```

`--quick` pins every sum type in the datum and redeemer to its first constructor: minutes instead of tens of minutes, at the cost of the paths behind the other constructors. Leave it out for the run that counts. The checks are one Lean module each under `Demo/<Validator>/`, built four at a time (`--jobs`). The exit code is 1 when a HOLE remains, 2 when a check got no verdict, 0 otherwise. The report for the buggy vault ends like this:

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
| REVIEW | The check fails but the behavior can be by design. The counterexample names the case to confirm or to waive. |
| WAIVED | A REVIEW or HOLE line that [`universal.json`](../universal.json) waives, with a reason, an owner and an expiry if given. |
| UNREACHED | No accepted spend exists for this action within the shape, so a "rejects" check for that action proved nothing. |
| UNKNOWN | Blaster gave no verdict for this check. Silence is never counted as a pass. |

## The candidates prototyped here

Every property below is a candidate, not an accepted entry: each one has its ticket (#22 to #37) and nothing is decided yet. This prototype covers six of them.

| Candidate | Statement | Severity |
| --- | --- | --- |
| UP-000, per action | Some realistic, ledger-valid spend with this redeemer is accepted. Otherwise funds are stuck, or the action needs a shape the generator lacks. | review |
| UP-001, per undeclared purpose | The script rejects every purpose its blueprint declares no handler for (mint, withdraw, publish, vote, propose), with that purpose's witness and redeemer entry present in the transaction. | hole |
| UP-002, per action | A realistic, ledger-valid spend with no signatories is rejected. | review |
| UP-004, per action | Some realistic, ledger-valid spend with this redeemer is rejected. Otherwise the action is always true. | hole |
| UP-005 | A realistic, ledger-valid spend with a malformed redeemer is rejected: any integer, and any constructor index the type lacks. Only when the blueprint types the redeemer. | hole |
| UP-011, per action | A spend accepted with its output back at the script, carrying any datum, is rejected once that output moves to a key address or to another script's address. | review |

UP-000 and UP-004 are stated backwards, as a universal claim that Blaster must falsify (`#blaster (solve-result: 1)`), the way the `cannot_unlock_nft` test in Input Output's (IOG) CardanoLedgerApiBlaster does. The falsifying witness is a working transaction, found by Blaster, not supplied by anyone.

## How a check is stated

The transaction is generic. Every list the shape covers holds up to two items, a Bool flag per item says whether it is present, and every value is open. Every sum type in the datum or the redeemer becomes a Bool-selected choice between its constructors, so a vesting beneficiary can be a key or a script. The continuing output carries a datum of the same shape with independent leaves, so it may differ from the input's. A mint, when present, lands in the continuing output, so the balance can absorb it. Blaster picks all the flags and values.

On the spend checks, the ledger rules from CardanoLedgerApi (`validScriptContext`) are a hypothesis, plus one rule the model does not enforce: no value below 1,000,000 lovelace. So every witness and counterexample is a transaction the chain would accept: it pays a fee, it balances, and its outputs are not dust. The purpose checks are unconditional, and each purpose context carries the purpose's witness: the mint entry, the withdrawal, the certificate, the vote or the proposal, plus the matching redeemer entry.

The script itself is loaded from the blueprint's `compiledCode` with `#import_uplc` and run through the CEK model with the shared predicates in [`Formal/Common.lean`](../Formal/Common.lean), one theorem per check.

## Results on 2026-10-22

Quick mode (`--quick`: sum types pinned to their first constructor), batches of four modules in parallel:

| Validator | Checks | Result | Time |
| --- | --- | --- | --- |
| `vault` | 9 | 8 pass; UP-011 review: a vault pays out anywhere by design | 1 min |
| `vault_buggy` | 9 | 6 holes: always-true `spend`, and all five undeclared purposes accepted; UP-002 waived; UP-011 review | 1 min |
| `linear_vesting` | 14 | 12 pass; UP-011 review on Claim and on Cancel, both pay out by design | 6.5 min |

`linear_vesting` is the compiled code from this repository's committed `onchain/plutus.json` (Aiken v1.1.22). The two demo vaults were compiled from `Demo/aiken/` with Aiken v1.1.19.

Full mode (every sum type a choice) on `linear_vesting`: not finished within 25 minutes; the Claim sanity pair alone was still running when the cap hit. Full mode finishes on the vaults (no sum types) in about a minute. Until the sum choices are generated as separate modules (see `Notes.lean`), quick mode is the practical run for vesting-sized contracts.

Two of IOG's own patterns were tried and are not the default here. `#prep_uplc` (apply the script once to a symbolic context) finished in 15 seconds on the vault but not within 5 minutes on vesting; it stays behind `--prep`. A fully open context with no shape, as in IOG's `SellNFT` tests, did not finish the vesting sanity check within 5 minutes either. The bounded shape is what finishes.

## Limits, in one line

A PASS holds within the generated shape: no reference inputs, withdrawals, certificates, datum hashes or tokens on inputs, at most two of each list. `Notes.lean` has the full list and what the review left open.
