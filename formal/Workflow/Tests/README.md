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

The aggregate command includes component units, property metadata checks, runner failure controls,
Input-to-Generator type-checking, real Executor/Reporter solver controls, and
both scenarios below. Each scenario already invokes its candidate-specific
checks. Optional manual integration probes are not additional suite runs.
Register new workflow test executables in `Runner.defaultSuites` so the aggregate
command includes them.

For focused scenario debugging:

```sh
lake exe workflow_up001_tests
lake exe workflow_up012_tests
```

| Scenario | Coverage | Definition/model source |
| --- | --- | --- |
| [UP001](UP001/README.md) | Passing and failing vaults, invalid input, and timeout | `Candidates.UP001` and fixed demo inputs |
| [UP012](UP012/README.md) | Four original vesting propositions, unsupported-profile handling, and a semantic negative control | `Candidates.UP012` plus the test-owned vesting profile |

[Unit checks](Unit/README.md) cover Input, generic Generator contracts, Executor,
and Reporter. The legacy executable names remain available for these checks and
existing integration controls.

Inputs and expected declarations are permanent test fixtures. Generated Lean
sources, compiler artifacts, logs, and reports appear only in the local ignored
`formal/output/` folders after a CLI run. The [file map](../CHECK-FILES.md) shows
where supporting definitions live.
