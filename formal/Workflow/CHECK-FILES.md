# Supporting files for candidate checks

Primary definitions and property metadata live in the
[property bank](../Formal/Properties/README.md). Context construction and model
metadata live in the [transaction-model bank](../Formal/TxModels/README.md).
Generated checks import this repository code rather than copying it into each
output directory. The old property-helper module keeps current context aliases.

## UP-001 context definitions

| Generated check | Supporting type and context builder |
| --- | --- |
| `otherPurpose_mint` | [`EveryMint` and `EveryMint.ctx`](../Formal/TxModels/Definitions/TxM001.lean) |
| `otherPurpose_withdraw` | [`EveryWithdraw` and `EveryWithdraw.ctx`](../Formal/TxModels/Definitions/TxM002.lean) |
| `otherPurpose_publish` | [`EveryPublish` and `EveryPublish.ctx`](../Formal/TxModels/Definitions/TxM003.lean) |
| `otherPurpose_vote` | [`EveryVote` and `EveryVote.ctx`](../Formal/TxModels/Definitions/TxM004.lean) |
| `otherPurpose_propose` | [`EveryPropose` and `EveryPropose.ctx`](../Formal/TxModels/Definitions/TxM005.lean) |
| `otherPurpose_spend`, when spend is undeclared | [`EverySpend` and `EverySpend.ctx`](../Formal/TxModels/Definitions/TxM006.lean) |

Each type holds a full `TxInfo` plus the fields for its purpose. Its `.ctx`
function uses [`mkCtx`](../Formal/TxModels/Common.lean) to assemble the
`ScriptContext`, with the raw redeemer supplied by the theorem. The vault demo
declares `spend`, so it generates the first five checks only.

## Generated files

The command creates `formal/output/run.XXXXXXXX/` and prints its exact path as
`Evidence:`. Inside that run folder:

| File | Definitions |
| --- | --- |
| `Generated/Workflow/Types.lean` | `program`, `args`, and `accepts`: the compiled validator, context conversion, and bounded execution predicate |
| `Generated/Workflow/Checks.lean` | The generated `otherPurpose_*` theorems, applying the shared UP-001 statement to the selected `Every*` contexts |

[`Candidates/UP001.lean`](../Candidates/UP001.lean) produces these files
and selects a context type for each undeclared purpose. Current UP-001 statements
apply [UP001/Definition.lean](../Formal/Properties/Universal/UP001/Definition.lean)
with literal `5000000` passed to `accepts`. The shared helper file also defines
`ledgerFuel`, `runFor`, and `rejectedWithin`; these are not the predicate or bound
used by the current UP-001 statements.

## Dependency definitions

These links point to the exact revisions in [`lake-manifest.json`](../lake-manifest.json).
Lake prepares local copies under `formal/.lake/packages/`.

| Definition | Pinned source |
| --- | --- |
| `TxInfo` and `ScriptContext` | [CardanoLedgerApi/V3/Contexts.lean](https://github.com/input-output-hk/CardanoLedgerApiBlaster/blob/577e3eb03b5be09354cfdb1c0d0c12e9e16541a0/CardanoLedgerApi/V3/Contexts.lean#L389) |
| `toTerm`, converting a context into a UPLC argument | [CardanoLedgerApi/IsData/Class.lean](https://github.com/input-output-hk/CardanoLedgerApiBlaster/blob/577e3eb03b5be09354cfdb1c0d0c12e9e16541a0/CardanoLedgerApi/IsData/Class.lean#L56) |
| `cekExecuteProgram` and `runSteps`, evaluating the compiled program | [PlutusCore/UPLC/CekMachine.lean](https://github.com/input-output-hk/PlutusCoreBlaster/blob/4ef48606303c45225d3ed2e2a87fc50280a763b7/PlutusCore/UPLC/CekMachine.lean#L242) |
| `blaster`, the theorem tactic | [Blaster/Command/Tactic.lean](https://github.com/input-output-hk/Lean-blaster/blob/402f6d22c1fc42e6e26255faac77e15b2450e4ab/Blaster/Command/Tactic.lean) |

The run's `execution.json` records the generated module paths, observed jobs,
and prepared module search path. Use the [quickstart](QUICKSTART.md) to run the
checks and find their generated sources and logs.

## UP-012 vesting profile

[UP012/Definition.lean](../Formal/Properties/Universal/UP012/Definition.lean)
holds one signer-removal statement and its applicability predicate.
[`Candidates/UP012.lean`](../Candidates/UP012.lean) applies them to Claim and Cancel;
[`Tests/UP012/Profile.lean`](Tests/UP012/Profile.lean) supplies the pinned artifact guard.
The models live in [TxM007](../Formal/TxModels/Definitions/TxM007.lean) and
[TxM008](../Formal/TxModels/Definitions/TxM008.lean). Each
output folder has three generated Lean files:

| File | Definitions |
| --- | --- |
| `Generated/Workflow/Types.lean` | Aliases for native vesting types, compiled program, `accepts`, and `rejects` |
| `Generated/Workflow/Tx.lean` | Aliases for native `ClaimLeaves`, `CancelLeaves`, `claim`, `cancel`, and their datum builder |
| `Generated/Workflow/Checks.lean` | `dropSigner_claim`, `dropSigner_cancel`, and both `_applies` statements |

Shared support comes from the same repository helper file:

- [`signatoriesOf` and `withSignatories`](../Formal/Universal/Properties.lean)
  read or replace the context's signatory list.
- [`Formal.TxModels.TxBuilder`](../Formal/TxModels/Common.lean)
  builds the supplied inputs, outputs, and spend contexts.
- [`rejectedWithin`](../Formal/Universal/Properties.lean#L26)
  requires rejection within the candidate's `ledgerFuel` bound of 1,000,000 steps.

These shapes have one signatory and remove the first key. The provider is an
experimental test of the pinned vesting artifact, with applicability checks;
it does not generate general required-signer checks for arbitrary validators.

## Catalogue and entry point

[Formal/Properties/Index.lean](../Formal/Properties/Index.lean) references categories
and their native definitions/metadata. [`Candidates/Catalogue.lean`](../Candidates/Catalogue.lean)
composes the supported generation adapters. [`ProductCLI.lean`](ProductCLI.lean)
supplies that resolver to [`Main.lean`](Main.lean); CLI.lean retains the legacy entry
point. The four reusable components do not import candidates
or scenario fixtures. Catalogue format and additional CLI selection modes remain
separate design decisions.
