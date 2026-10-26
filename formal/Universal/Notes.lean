/-!
# Universal checks: design notes

These notes live next to the generated modules so `lake build Universal` carries them. The
generator is `scripts/universal.py`; the user-facing summary is `Universal/README.md`.

## The idea

A universal property is a security property stated over what every validator shares: the compiled
script as a black box, the script context around it, and what the compiler already reports in the
blueprint (handlers, datum and redeemer shapes). The validator's author writes nothing. The
catalogue writes each check once; the generator instantiates it on a validator; Blaster proves it
or returns a counterexample; a config file switches a check off, or waives a whole check with a
reason and an expiry date.

Prior art the design leans on: Certora's built-in rules (`use builtin rule sanity;`: one line to
enable, a counterexample on failure), Tweag's cooked-validators attacks (tamper with a working
transaction: datum hijacking, redeemer tampering, validity tampering), IOG's own tests in
CardanoLedgerApiBlaster (`cannot_unlock_nft`, stated backwards with `solve-result: 1`; one
structure, `SpendingInput`, for every open value), Kani's proof harnesses (a bound on every list,
the solver picks how many items), IOG's conformance-test generator in PlutusCoreBlaster
(`scripts/GenConformanceTests.lean`, which writes one Lean module per test from a template), plus
Lean-blaster's toy vesting example, whose `reject_other_purposes` is UP-001 on a model.

## The candidates prototyped here

All are candidates, none accepted; each has its ticket (#22 to #37).

- UP-000, per action: some realistic, ledger-valid spend with this redeemer is accepted.
  Stated backwards and falsified; the witness is printed. Severity review.
- UP-001, per undeclared purpose: the script rejects mint, withdraw, publish, vote, propose
  when its blueprint declares no handler, with the purpose's witness in the transaction. Hole.
- UP-002, per action: a ledger-valid spend with no signatories is rejected. Review.
- UP-004, per action: some realistic, ledger-valid spend with this redeemer is rejected.
  Stated backwards and falsified. Hole: an action that always accepts is an always-true branch.
- UP-005: a ledger-valid spend with a malformed redeemer (any integer, any unknown constructor
  index) is rejected. Hole. Two theorems, one module each.
- UP-011, per action: accepted with the continuing output at the script, under any datum of the
  blueprint's shape, then rejected once that output moves to a key or to a different script.
  Review: paying out can be intended.

## The shape

The open values are the fields of one `Holes` structure per validator; the transaction is
composed from the builders in `Universal/Harness.lean`; each check quantifies over one
`h : Holes` and pins the fields it needs with hypotheses. Blaster splits the structure into its
fields, so nothing has to list them, and a counterexample comes back as one `Holes` value that
the report prints field by field.

Every covered list holds up to two items, a Bool flag per item. Every value is open. Every sum
type in the datum or redeemer is a Bool choice between constructors. Every spend check uses one
context, in which the continuing output's datum has its own leaves and its own choices, so a
contract that must change its datum (a counter that counts up) is reachable. A mint, when present,
lands in the continuing output so the balance rule can absorb it. Blaster picks all flags and
values. Only UP-011 lets the output go to another script; the other checks, UP-001 included, pin
that flag, because an open choice a check never uses still costs search time. When UP-011 moves the output to another script, that
script is assumed different from the own one (`h.payee ≠ own`); without it the solver could name
the own script, the moved output would equal the original, and UP-011 could never pass.

Not covered: reference inputs, withdrawals on spends, certificates, datum hashes, tokens on
inputs, a third item in any transaction list, a finite upper validity bound. A list inside a datum
always holds exactly one item, and a map inside a datum is always empty. A PASS holds within the
shape.

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

An `if c then A else B` inside one theorem doubles the paths of one Z3 problem. So full mode
writes one module per combination of constructors, each fixed by hypotheses, so each module
explores one combination. A sum nested inside a constructor (a credential inside `Some`) is split
only under that constructor, so no combination is checked twice. A check gets at most 16 modules
(`--max-cases`). When the combinations do not fit, only the outermost sums are split, as many as
fit, in order, and the rest stay open choices inside each module: every combination is still
covered, in fewer and harder modules. A datum holding two addresses, for example, has 64
combinations, and the continuing output's datum as many again; full mode splits the input datum's
four outermost sums into 16 modules and leaves the rest open.

The generator builds each theorem from its parts (the case's hypotheses, then the check's), never
by editing rendered text. A first version of the split, run on 2026-10-23 and never committed,
inserted the hypotheses by searching the text and missed UP-011, whose first line ended
differently. Its eight vesting case modules ran unsplit: the four for Claim took about 3.4 hours
each and the four for Cancel about 11 minutes, while every other case module took 9 to 136
seconds.

Each module has a time limit, 600 seconds by default (`--timeout`), on the wall clock: the script
builds each module in its own process group and stops Lean and Z3 together when time runs out,
and the module reports UNDETERMINED. A check split into 16 modules can therefore take up to 16
times the limit, spread over the parallel jobs. Blaster's own `timeout` option bounds only the Z3
call, not the translation before it, and Blaster switches off Lean's `maxHeartbeats`, so neither
bounds a run on its own.

Measured on 2026-10-26 on the fork's pins, four modules at a time: the two vaults take 89 seconds
together (9 modules each, no sum types); vesting takes 4 minutes in quick mode (15 modules) and 35
minutes in full mode (180 modules: 16 cases for each spend check, 4 for each UP-001), with the
same verdicts, and no module reached the time limit. The uncommitted first version of the split
took 3.7 hours. In full mode, Claim is reachable only when the beneficiary is a key and Cancel only
when the locker is a key: within the shape only a key can authorize, so the checks in the other
cases are UNREACHED.

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
the script info. The model only requires a positive amount on an output, so two more hypotheses
stand in for the ledger's minimum, one per kind of claim:

- `ledgerFloor`: lovelace ≥ 689,600 on every input and output, the ledger's minimum for any
  output (4,310 lovelace per byte times the 160-byte overhead, CIP-55). Every real transaction
  meets it, so a universal claim (UP-002, UP-005, UP-011) that assumes only this covers every
  amount the chain allows.
- `realistic`: lovelace ≥ 1,000,000 everywhere, for the existence claims (UP-000, UP-004), so a
  witness is not dust. It is close to the ledger, not exact: the real minimum grows with the
  output's size, so an output with a datum and tokens can need more than 1 ada.

The purpose checks are unconditional: a purpose context that the ledger would reject is still a
context the script must reject.

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

A second review on 2026-10-26 compared each design choice with prior art and asked whether it is
the Lean way or a workaround.

- Matches prior art: one module per check written from a template (IOG's conformance-test
  generator); one structure for every open value (IOG's `SpendingInput`); a Bool flag per optional
  item (Kani's bounded lists); existence claims stated backwards with `solve-result: 1` (IOG's
  SellNFT tests); one module per combination of constructors (Blaster does no case analysis itself,
  and its README advises splitting the goal with `by_cases`; a module per case does the same and
  also runs in parallel).
- Bugs, fixed: UP-011 could never pass (the other script could be the own one); a first version
  of the case split missed UP-011 (above); lake did not rebuild when the compiled contract changed, because the
  code sat in a separate file that lake does not track (the justfile's `invalidate_lean` works
  around the same gap). The code is now written into `Base.lean`, so lake rebuilds.
- Workarounds, fixed: one verdict per file read from Lean's text, so a file with two theorems could
  hide one, as a solver timeout in UP-005's second theorem would have hidden behind the first
  one's Valid (now one declaration per module, and the script reads Blaster's exact messages); the
  exit code ignored UNREACHED (now 2); the solver timeout did not bound the time
  (above); `#blaster (solve-result: 1)` reports a solver timeout only as a warning, so the build
  passed (now `warningAsError` on that command, so `lake build` fails on it).
- Stopgaps, kept and named: `realistic` (Hypotheses); quick mode; Python, which the Nix shell now
  pins (the lasting form is below).
- Open: `lake build` is not yet the whole gate. A waived check, and a case that is unreachable by
  design (Cancel when the locker is a script), still fail the build; only the script's report
  applies `universal.json`. Making the build the gate needs the expected outcome of each module
  written into its source, as IOG's conformance tests keep an expected file per test. How a user
  records those outcomes is part of the developer workflow (issue #39).

A review of those fixes, the same day, found more, now fixed: the witness parser shifted every
field after a value Lean wrapped onto two lines, so it printed wrong witnesses; UP-011 took its
reachability from UP-000, whose context repeated the input datum, so every spend check now uses
the open output datum; a case counted as UNREACHED when its UP-000 merely had no verdict; a sum of
three constructors, or one nested in another, gave duplicate cases and contradictory labels, and a
datum holding one address gave 720 modules; a datum leaf could take a fixed field's name
(`payee2`), so the `Holes` structure did not build; a `Base` that did not build exited 1, the code
for a HOLE; a waiver ignored its expiry date and `"state": "off"`.

## Candidates not yet prototyped

UP-006 to UP-008 (output back to the script: declared datum shape, same staking credential, at
most N tokens); UP-009 (hashed-datum input still spendable; blocked: the pinned ledger model treats
a resolved datum on a hashed-datum input as invalid); UP-010 (two script inputs, one output);
UP-012 (one signer removed); UP-013 (unbounded validity range, off by default); UP-014 to UP-016
(datum tampering, output reordering, own-policy token duplication). UP-010 and UP-012 need a
definition of payout and of required signer first.

## Intended form

The Python generator is a stopgap. The intended form is the same generator as a Lean program
(`lean_exe`), the way IOG's `gen_conformance_tests` in PlutusCoreBlaster writes its test modules
from templates. This replaces the earlier plan of a Lean command that reads the blueprint: IOG's
own generator writes files, and a file per check is what lets lake build them in parallel and
cache them. Tracked with the PRs on the fork.

Proof harness experiment, 2026-10-23 (issue #38). UP-002 on the vault was restated by hand over
one structure of holes (`Holes`, 23 fields), with the transaction composed from small builders
(`optList`, `upTo2`, `output`, `tx`, ...) instead of one generated definition, and the property
pinning its fields with hypotheses (`h.sig1 = false → ...`). Same verdict (Valid), same time
(6 s against 8 s for the generated module, both including Nix startup), and `rfl` shows the
composed context is the generated one. So Blaster splits a structure into its fields, and the
generator now emits a structure plus builders instead of listing every open value: same verdicts
on all three validators, and vesting runs in 4 minutes instead of 6.5.

Names: the compiled code is an `abbrev script` inside each validator's namespace, decoded by
PlutusCoreBlaster's `singleCborEncodedScriptFromHexM`, so two validators cannot clash. Only
`#prep_uplc` (behind `--prep`) still declares its name outside any namespace, so the generator
names it after the validator (`universalVaultPrepared`); `Demo/NoClash.lean` imports every `Base`
and fails to build if two validators ever share a name.
-/
