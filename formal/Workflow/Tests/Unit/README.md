# Component unit checks

Run from `formal/`:

```sh
lake exe workflow_input_tests
lake exe workflow_generator_tests
lake exe workflow_executor_tests
lake exe workflow_reporter_tests
lake exe workflow_executor_integration
lake exe workflow_reporter_integration
```

| Area | Coverage |
| --- | --- |
| `Input/Tests.lean` | Selection, metadata preservation, code decoding, and malformed inputs |
| `Generator/Tests.lean` | Generic contracts with stub providers, namespace validation, and empty plans |
| `Executor/Tests.lean` | Controlled compiler diagnostics, deadlines, output isolation, and process cleanup |
| `Reporter/Tests.lean` | Expectation comparison, missing/duplicate observations, statuses, and report files |

`workflow_generator_tests` runs only the generic Generator contract checks.
The UP001 and UP012 workflow suites run their own candidate-specific checks.

The Input fixture preserves its original synthetic metadata and small decodable
program `480100002221200101`, from the pinned [script-encoding test](https://github.com/input-output-hk/PlutusCoreBlaster/blob/4ef48606303c45225d3ed2e2a87fc50280a763b7/PlutusCore/UPLC/ScriptEncoding/Tests.lean#L12).
It provides parser evidence rather than a validator proof.

`Fixtures/outcomes.lean.txt` is the unchanged shared real-solver control for
Executor and Reporter: one valid equation and one false quantified equation,
including indented counterexample values. `Reporter/Fixtures/summary.txt`
fixes the minimal text format for a synthetic observation. Neither fixture is
proof evidence for a Cardano validator. The solver controls retain Blaster's
SMT trust boundary.
