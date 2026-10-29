# Supporting files for UP-001

The generated checks import their shared context definitions from
[`formal/Formal/Universal/Properties.lean`](../Formal/Universal/Properties.lean).
These definitions already live in the repository. Each run imports them rather
than generating copies in its output directory.

## Context definitions

| Generated check | Supporting type and context builder |
| --- | --- |
| `otherPurpose_mint` | [`EveryMint` and `EveryMint.ctx`](../Formal/Universal/Properties.lean#L49) |
| `otherPurpose_withdraw` | [`EveryWithdraw` and `EveryWithdraw.ctx`](../Formal/Universal/Properties.lean#L56) |
| `otherPurpose_publish` | [`EveryPublish` and `EveryPublish.ctx`](../Formal/Universal/Properties.lean#L63) |
| `otherPurpose_vote` | [`EveryVote` and `EveryVote.ctx`](../Formal/Universal/Properties.lean#L71) |
| `otherPurpose_propose` | [`EveryPropose` and `EveryPropose.ctx`](../Formal/Universal/Properties.lean#L78) |
| `otherPurpose_spend`, when spend is undeclared | [`EverySpend` and `EverySpend.ctx`](../Formal/Universal/Properties.lean#L41) |

Each type holds a full `TxInfo` plus the fields for its purpose. Its `.ctx`
function uses [`mkCtx`](../Formal/Universal/Properties.lean#L36) to assemble the
`ScriptContext`, with the raw redeemer supplied by the theorem. The vault demo
declares `spend`, so it generates the first five checks only.

## Generated files

The command creates `formal/output/run.XXXXXXXX/` and prints its exact path as
`Evidence:`. Inside that run folder:

| File | Definitions |
| --- | --- |
| `Generated/Workflow/Types.lean` | `program`, `args`, and `accepts`: the compiled validator, context conversion, and bounded execution predicate |
| `Generated/Workflow/Checks.lean` | The generated `otherPurpose_*` theorems, which use the shared `Every*` contexts |

[`Generator/OtherPurpose.lean`](Generator/OtherPurpose.lean) produces these files
and selects a context type for each undeclared purpose. Current UP-001 statements
pass literal `5000000` to `accepts`. The shared helper file also defines
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
