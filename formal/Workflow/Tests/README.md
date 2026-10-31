# Workflow tests

The four reusable components have separate unit coverage. UP001 and UP012 are
the two complete workflow scenarios; they reference candidate implementations
instead of defining candidate logic in the engine.

From `formal/`, run all workflow tests with verbose logs:

```sh
./plutus-upv test
```

With `formal/` on your shell's `PATH`, use `plutus-upv test` from any directory.
The runner builds explicit test targets, executes suites sequentially, and saves
logs and summaries under ignored `formal/output/test.XXXXXXXX/`. A build failure
stops the run; a suite failure allows the remaining independent suites to run.
Only a complete successful test run returns zero. Expected negative controls
print FAIL or INCONCLUSIVE without making their enclosing suite fail.

The aggregate command includes component units, metadata, run evidence, selection,
output controls, and installer/launcher checks. It also runs real app/core solver cases, runner failure
controls, Input-to-Generator type-checking, Executor/Reporter solver controls, and
both scenarios below. Each scenario invokes its candidate-specific checks.
Optional manual integration probes are not additional suite runs.
Register new workflow test executables in `Runner.defaultSuites` so the aggregate
command includes them.

For focused scenario debugging:

```sh
lake exe workflow_up001_tests
lake exe workflow_up012_tests
lake exe workflow_single_check_tests
lake exe workflow_app_tests
lake exe workflow_selection_tests
```

| Scenario | Coverage | Definition/model source |
| --- | --- | --- |
| [UP001](UP001/README.md) | Passing and failing vaults, invalid input, and timeout | `Candidates.UP001` and fixed demo inputs |
| [UP012](UP012/README.md) | Four original vesting propositions, unsupported-profile handling, and a semantic negative control | `Candidates.UP012` plus the test-owned vesting profile |

The UP001/UP012 scenario harnesses preserve the legacy `universal` CLI contract.
The app control suite checks orchestration and terminal/index behavior. The
single-check suite runs actual compiled-validator goals through the app and core.
This reuses the existing solver cases.

[Unit checks](Unit/README.md) cover Input, generic Generator contracts, Executor,
and Reporter. The legacy executable names remain available for these checks and
existing integration controls.

The [single-check suite](SingleCheck/Tests.lean) checks the callable core, exact
selected theorem sets, assessment, and retained evidence. It runs UP-001 minting
against the passing/failing vaults and the UP-012 Claim/application pair through
the app and core APIs. `lake exe workflow_single_check_tests --unit` restricts that test executable
to adapter, assessment, and controlled-process checks without the real solver cases.

Inputs and expected declarations are permanent test fixtures. Generated Lean
sources, compiler artifacts, logs, and reports appear only in the local ignored
`formal/output/` folders after a CLI run. The [file map](../Docs/DEVELOPER-GUIDE.md#generated-goals-and-supporting-files) shows
where supporting definitions live.
