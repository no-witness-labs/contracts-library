# Vault demo

A small Aiken project for inspecting Plutus UPV's generated Lean files and
execution evidence. Both validators have no script parameters and declare a
spending handler.

| Validator | Behavior | UP-001 result when the five obligations complete |
| --- | --- | --- |
| `vault.vault` | Requires the datum's owner to sign spending; rejects other purposes | Five PASS |
| `vault_buggy.vault_buggy` | Deliberately accepts spending and other purposes | Five FAIL |

UP-001 checks undeclared purposes. These checks do not establish the spending
handler's authorization correctness. The buggy validator is a negative control
for the workflow.

## Build and run

Use Aiken 1.1.21 and the pinned stdlib 3.0.0 dependency. From this directory:

```sh
aiken build
plutus-upv run --check UP-001 --timeout-ms 120000
```

Install the app first with [formal/install.sh](../../../../install.sh) if needed.
The app uses this directory's newly built `plutus.json`. The explicit timeout
gives each check up to two minutes; the app's general default remains 30 seconds.
The demo's blueprint, build cache, and optional generated artifacts stay ignored
by Git. No automatic Aiken build is added to the app or aggregate workflow tests.

## Inspect the output

The terminal prints the run folder and `run.json` paths. Outputs remain under
the app checkout's `formal/output/`, with separate folders for each invocation.

For each validator, the five undeclared purposes produce five pairs of Lean
files: `Types.lean` embeds the compiled script and its evaluation interface;
`Checks.lean` applies UP-001 to one purpose model. Each pair lives under:

```text
validators/<validator>/UP-001-v1-<TxM-ID>/Generated/
```

The models are TxM-001 (mint), TxM-002 (withdraw), TxM-003 (publish), TxM-004
(vote), and TxM-005 (propose). TxM-006 selects the declared spend purpose and
therefore produces an INCONCLUSIVE no-obligation result with no Lean check.
Expect 20 generated `.lean` files across both validators when generation succeeds,
plus result JSON, execution manifests, input snapshots, and compiler logs.
A timed-out check keeps its generated sources and reports INCONCLUSIVE.

This example does not produce `Tx.lean`; current UP-001 models are imported
directly. The maintained property/model/helper definitions also remain in the
repository under the current output design. The existing UP-012 vesting scenario
demonstrates the optional `Tx.lean` adapter.

The app's exit code describes completion and retention. A deliberately failing
vault check can therefore appear in a completed run with exit code 0; inspect
the individual results and logs.

## Provenance and regression fixtures

The two validator sources are copied unchanged from the pinned
[UP-001 fixture project](../../UP001/Inputs/), originally attributed to
[PR #47's demo](https://github.com/no-witness-labs/contracts-library/tree/0dde8ae76e3f8a239bf06685f72327aed4a7c3ef/formal/Universal/Demo/aiken).
The source snapshot records Apache-2.0 licensing. This editable project has its
own package name and compiler setting; building it does not update the pinned
fixture's sources, dependency lock, or `plutus.json`.
