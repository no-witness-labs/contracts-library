# Workflow tests

The four reusable components have separate unit coverage. UP001 and UP012 are
the two complete workflow scenarios; they reference candidate implementations
instead of defining candidate logic in the engine.

From `formal/`, run the slow workflow suites sequentially:

```sh
lake exe workflow_up001_tests
lake exe workflow_up012_tests
```

| Scenario | Coverage | Definition/model source |
| --- | --- | --- |
| [UP001](UP001/README.md) | Passing and failing vaults, invalid input, and timeout | `Candidates.UP001` and fixed demo inputs |
| [UP012](UP012/README.md) | Four original vesting propositions and unsupported-profile handling | `Candidates.UP012` plus the test-owned vesting profile |

[Unit checks](Unit/README.md) cover Input, generic Generator contracts, Executor,
and Reporter. The legacy executable names remain available for these checks and
existing integration controls.

Inputs and expected declarations are permanent test fixtures. Generated Lean
sources, compiler artifacts, logs, and reports appear only in the local ignored
`formal/output/` folders after a CLI run. The [file map](../CHECK-FILES.md) shows
where supporting definitions live.
