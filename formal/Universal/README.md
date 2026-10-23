# Universal checks

A universal check is a security property that applies to any compiled validator, with nothing written by the validator's author. This folder holds a prototype. A generator reads a validator's blueprint (`plutus.json`) and writes the checks as Blaster theorems for that validator. It then runs them and prints a pass or fail report, with a counterexample for each failure.

The author only compiles. The same checks ran on the two demo vaults in [`Demo/aiken/`](Demo/aiken/) and on the catalogue's own [`linear_vesting`](../../onchain/validators/linear_vesting.ak). The generated modules are committed, so `lake build Universal.Demo.Linear_vesting` reproduces the vesting result without Python or Aiken.

## Run it

From `formal/`, inside the Nix shell (`nix develop`), with `aiken` built blueprints in place:

```sh
python3 scripts/universal.py --blueprint Universal/Demo/aiken/plutus.json vault vault_buggy
python3 scripts/universal.py --blueprint ../onchain/plutus.json linear_vesting
```

Each validator takes between 30 and 70 seconds. The report for the buggy vault ends like this:

```text
❌ HOLE    UP-001/mint      rejects undeclared purpose `mint`
           consequence: anyone could mint or burn tokens under this script's hash
⚠️  WAIVED  UP-002           rejects a spend with no signatories
           waived: demo waiver: pretend this vault is permissionless by design
```

HOLE means the check fails and almost no contract should fail it. REVIEW means the check fails but the behavior can be by design; the counterexample names the case to confirm or to waive. A waiver is one line in [`universal.json`](../universal.json), with a reason, and shows up in the report as WAIVED.

## The checks

| Check | Statement | Severity |
| --- | --- | --- |
| UP-000, per action | Some ledger-valid spend with this redeemer is accepted. Otherwise funds are stuck. | hole |
| UP-001, per undeclared purpose | The script rejects every purpose its blueprint declares no handler for: mint, withdraw, publish, vote, propose. | hole |
| UP-002 | A ledger-valid spend with no signatories is rejected. | review |
| UP-004, per action | Some ledger-valid spend with this redeemer is rejected. Otherwise the action is always true. | hole |
| UP-005 | A ledger-valid spend with a redeemer of the wrong shape is rejected. Only when the blueprint types the redeemer. | hole |
| UP-011 | A ledger-valid spend accepted with its output back at the script is rejected once that output moves to a key address. | review |

UP-000 and UP-004 are stated backwards, as a universal claim that Blaster must falsify (`#blaster (solve-result: 1)`), the way the `cannot_unlock_nft` test in Input Output's (IOG) CardanoLedgerApiBlaster does. The falsifying witness is a working transaction, found by Blaster, not supplied by anyone.

## How a check is stated

The transaction is generic: every list in the script context holds up to two items, a Bool flag per item says whether it is present, and every value is open. Blaster picks the flags and the values. On the spend checks, the ledger rules from CardanoLedgerApi (`validScriptContext`) are a hypothesis. So every counterexample is a transaction the chain would accept: it pays a fee and it balances. The purpose checks are unconditional.

The script itself is loaded from the blueprint's `compiledCode` with `#import_uplc` and run through the CEK model with the shared predicates in [`Formal/Common.lean`](../Formal/Common.lean), one theorem per check.

## Results on 2026-10-22

| Validator | Checks | Result | Time |
| --- | --- | --- | --- |
| `vault` | 9 | 8 pass; UP-011 review: a vault pays out anywhere by design | 29 s |
| `vault_buggy` | 9 | 6 holes: always-true `spend`, and all five undeclared purposes accepted; UP-002 waived | 27 s |
| `linear_vesting` | 12 | 11 pass; UP-011 review: with `total = 0` nothing is at stake, so the output may go anywhere | 64 s |

Two of IOG's own patterns were tried and are not the default here. `#prep_uplc` (apply the script once to a symbolic context) finished in 15 seconds on the vault but not within 5 minutes on vesting; it stays behind `--prep`. A fully open context with no shape, as in IOG's `SellNFT` tests, did not finish the vesting sanity check within 5 minutes either. The bounded shape is what finishes.

## Limits

- The shape bounds what Blaster can find: at most two inputs, two outputs, two signers, one mint, no reference inputs, withdrawals or certificates, no datum hashes. A check that needs a shape outside this cannot fail, so it reads as a pass. Widening the shape is the main lever.
- Parameterized validators are not handled; apply the parameters first.
- A Blaster `Valid` is the solver's verdict with no proof term, as for every proof in this repository.
- The generator is a Python prototype. The intended form is a Lean command that reads the blueprint, in the style of `#import_uplc`, with a Node wrapper for the report if one is needed, matching the repository's tooling.

## Candidates not yet generated

- UP-006 to UP-008: an output back to the script carries a datum of the declared shape, keeps the staking credential, and holds at most N tokens.
- UP-009: a hashed-datum input can still be spent.
- UP-010: two script inputs with one output are rejected.
- UP-012: removing one signer is rejected.
- UP-013: an unbounded validity range is rejected. Off by default.
- UP-014 to UP-016: datum tampering, output reordering and own-policy token duplication, from the cooked-validators attack set.

UP-010 and UP-012 need a definition of "payout" and "required signer" before their generic form stops producing misleading failures.
