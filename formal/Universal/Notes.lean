/-!
# Universal checks: design notes

These notes live next to the generated modules so `lake build Universal` carries them. The
generator is `scripts/universal.py`; the user-facing summary is `Universal/README.md`.

## The idea

A universal property is a security property stated over what every validator shares: the compiled
script as a black box, the script context around it, and what the compiler already reports in the
blueprint (handlers, datum and redeemer shapes). The validator's author writes nothing. The
catalogue writes each check once; the generator instantiates it on a validator; Blaster proves it
or returns a counterexample; a config file switches a check off or waives one case with a reason.

Prior art the design leans on: Certora's built-in rules (`use builtin rule sanity;`: one line to
enable, a counterexample on failure), Tweag's cooked-validators attacks (tamper with a working
transaction: datum hijacking, redeemer tampering, validity tampering), and IOG's own tests in
CardanoLedgerApiBlaster (`cannot_unlock_nft`, stated backwards with `solve-result: 1`), plus
Lean-blaster's toy vesting example, whose `reject_other_purposes` is UP-001 on a model.

## The candidates prototyped here

All are candidates, none accepted; each has its ticket (#22 to #37).

- UP-000, per action: some realistic, ledger-valid spend with this redeemer is accepted.
  Stated backwards and falsified; the witness is printed. Severity review.
- UP-001, per undeclared purpose: the script rejects mint, withdraw, publish, vote, propose
  when its blueprint declares no handler, with the purpose's witness in the transaction. Hole.
- UP-002, per action: a realistic, ledger-valid spend with no signatories is rejected. Review.
- UP-004, per action: some realistic, ledger-valid spend with this redeemer is rejected.
  Stated backwards and falsified. Hole: an action that always accepts is an always-true branch.
- UP-005: a malformed redeemer (any integer, any unknown constructor index) is rejected. Hole.
- UP-011, per action: accepted with the continuing output at the script, carrying any datum, then
  rejected once that output moves to a key or another script. Review: paying out can be intended.

## The shape

Every covered list holds up to two items, a Bool flag per item. Every value is open. Every sum
type in the datum or redeemer is a Bool choice between constructors. The continuing output's
datum has its own leaves. A mint, when present, lands in the continuing output so the balance rule
can absorb it. Blaster picks all flags and values. Only UP-011 opens the output datum and the
foreign-script destination; the other checks pin them, because an open choice a check never uses
still costs search time.

Not covered: reference inputs, withdrawals on spends, certificates, datum hashes, tokens on
inputs, a third item in any list, a finite upper validity bound. A PASS holds within the shape.

## Cost, and the two speed controls

Blaster's time grows with the number of independent choices the contract actually reads: each
one can double the paths through the interpreter model. Vesting reads its datum deeply, so the
sum-type choices (key or script for the beneficiary and the locker) and the second datum made a
one-minute run take far longer. Two controls:

- One Lean module per check (`Universal/Demo/<Validator>/UP...lean`, all importing `Base.lean`),
  so `lake build` runs the checks in parallel on every core instead of one after another.
- `--quick`: pin every sum type to its first constructor. Faster and weaker: a path behind the
  other constructors is not exercised, which is exactly what the review found. Use it to iterate,
  and the full mode for the result that counts.

Measured on 2026-10-22 and 2026-10-23, batches of four: quick mode takes 1 minute per vault and
6.5 minutes for vesting (the committed Aiken v1.1.22 build); full mode takes about a minute per vault (no sum types) and did not finish on vesting
within 25 minutes, with the Claim sanity pair still running. An `if c then A else B` inside one
theorem doubles the paths of one Z3 problem. The next step is to generate one module per
combination of datum constructors instead (as the redeemer actions already are), so each module
costs what quick mode costs and the parallel build absorbs the count: two sums give four
modules per check, not one module twice as hard.

## Why the shape, and not the open context

IOG's documented pattern leaves the whole `ScriptContext` open under `validSpendingContext`
and applies the script once with `#prep_uplc`. Tested here on 2026-10-22 against the fork's
pins: on the demo vault, `#prep_uplc` finished in 15 s; on `linear_vesting` neither `#prep_uplc`
(60000 steps) nor the fully open sanity check finished within 5 minutes. The vesting README in
this repository reports the same for its own fully quantified theorems. IOG's largest example,
the Plinth auction, also uses a hand-built fixed shape. The bounded shape with open values is what
finishes on a real contract, in about a minute without the sum-type choices and the second datum.

## Hypotheses

`valid ctx := validScriptContext ctx = true` (CardanoLedgerApi, pinned version), so every witness
and counterexample pays a fee, balances, has sorted inputs and signers, and a datum that matches
the script info. `realistic` adds lovelace ≥ 1,000,000 on every input and output, since the model
only requires a positive amount. The purpose checks are unconditional: a purpose context that the
ledger would reject is still a context the script must reject.

## Review history

A review pass on 2026-10-22 (five skeptics, five refuters, one reader in the role of an IOG
maintainer) confirmed nineteen ways a check could give a wrong verdict, from two causes.

1. Too little was open: a `Data` redeemer was the constant 0; nested sum types were their first
   constructor (so a script-credential beneficiary was never exercised); the mint flag could never
   be on under the balance rule with ada-only outputs; the continuing output always repeated the
   input datum (so UP-011 held vacuously for contracts that must change the datum); purpose
   contexts lacked the purpose's witness and redeemer entry; UP-002 and UP-011 ran only for the
   first action. Fixed: see The shape and The checks above.
2. The report trusted silence: a check with no Blaster message counted as Valid, and a "rejects"
   check passed when no accepted spend existed for its action. Fixed: silence is UNKNOWN, those
   checks are UNREACHED, and the exit code is non-zero on a HOLE.

Still open from the review: the ledger model does not check hash lengths, so a witness may use a
one-byte key; UP-000's witness may be a datum no deployment would write (printed, so a reader can
judge); the shape gaps listed above.

## Candidates not yet prototyped

UP-006 to UP-008 (output back to the script: declared datum shape, same staking credential, at
most N tokens); UP-009 (hashed-datum input still spendable; blocked: the pinned ledger model treats
a resolved datum on a hashed-datum input as invalid); UP-010 (two script inputs, one output);
UP-012 (one signer removed); UP-013 (unbounded validity range, off by default); UP-014 to UP-016
(datum tampering, output reordering, own-policy token duplication). UP-010 and UP-012 need a
definition of payout and of required signer first.

## Intended form

The Python generator is a stopgap. The intended form is a Lean command that reads the blueprint
in the style of `#import_uplc`, with a Node wrapper for the report if one is needed, matching the
repository's tooling. Tracked with the PRs on the fork.

Proof harness experiment, 2026-10-23 (issue #38). UP-002 on the vault was restated by hand over
one structure of holes (`Holes`, 23 fields), with the transaction composed from small builders
(`optList`, `upTo2`, `output`, `tx`, ...) instead of one generated definition, and the property
pinning its fields with hypotheses (`h.sig1 = false → ...`). Same verdict (Valid), same time
(6 s against 8 s for the generated module, both including Nix startup), and `rfl` shows the
composed context is the generated one. So Blaster splits a structure into its fields, and the
generator can emit a structure plus builders instead of listing every open value.

Names: `#import_uplc` and `#prep_uplc` declare their name outside any namespace, so the generator
names them after the validator (`universalVaultScript`); `Demo/NoClash.lean` imports every
`Base` and fails to build if two validators ever share a name.
-/
