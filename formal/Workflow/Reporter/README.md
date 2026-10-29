# Reporter component

Reporter compares Executor observations with the jobs' declared expectations.
It produces a plain-text summary, a small JSON report, and an exit code. This
first version has no branding, rich layouts, expanded narrative, or waiver
handling.

## Outcomes

| Status | Meaning | Exit code |
| --- | --- | --- |
| PASS | Every requested job has a conclusive result matching its expectation | 0 |
| FAIL | A conclusive result differs from its expectation, with no incomplete result | 1 |
| INCONCLUSIVE | Execution was incomplete, evidence was missing or inconsistent, or no jobs ran | 2 |

An expected Falsified result can produce PASS. Reporter uses job metadata rather
than property-specific rules. Inconclusive results take precedence over failures.
Incomplete runs make every row inconclusive, while JSON preserves the original
observations. Missing, duplicate, unrequested, or changed job observations
cannot produce a passing report.

Statuses apply to the stated check scope. A report does not establish general
validator safety. The JSON retains each job's expected and observed result,
scope, issues, and a reference to Executor's detailed evidence.

## API

Import `Workflow.Reporter` and use:

- `Workflow.Reporter.build plan execution` to construct a report from typed data.
- `Workflow.Reporter.failure target message` for an input or preparation error.
- `report.text`, `report.toJson`, and `report.exitCode` for presentation and CI.
- `report.write directory` to save `report.txt` and `report.json`.

The component reads no blueprint, starts no process, and queries no solver.
Writing is explicit; the caller chooses and owns the output directory. Raw
diagnostics and generated sources remain in Executor's evidence directory.

## Prototype command

With the pinned dependencies and tools prepared, run from `formal/`:

```sh
lake exe universal /path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
```

The thin `Workflow.Main` entry point connects Input, Generator, Executor, and
Reporter. Providers live in Generator's ordinary Lean catalogue; the default is
its first registered provider. The first provider supports unparameterized
UP-001 targets. The command requires the prepared `LEAN_PATH` supplied by
`lake exe` and performs no dependency installation.

The default execution budget is 30,000 ms. The option controls Executor's shared
module budget; package builds, input reading, generation, and reporting add
overhead. The command prints the summary and JSON path, saves both report
formats, and preserves the input snapshot. It writes an inconclusive report for
input, provider-selection, and preparation errors too.

The CLI saves each run under `formal/output/run.XXXXXXXX/` and prints its exact
path. Earlier run directories remain intact. Input errors have report files
without generated Lean sources; executed jobs also retain sources, compiler
outputs, logs, and `execution.json`.

The command does not apply the Python prototype's `universal.json` waivers.
Unknown options return an inconclusive usage error. Standalone CBOR, additional
properties, typed parameter generation, and portable packaging remain later
work.

## Tests

From `formal/`:

```sh
lake build Workflow workflow_reporter_tests workflow_reporter_integration universal
lake exe workflow_reporter_tests
lake exe workflow_reporter_integration
```

The isolated unit harness constructs plans and observations directly. It checks
matching results, expected counterexamples, mismatches, incomplete runs, changed
metadata, missing and duplicate jobs, precedence, the plain summary fixture,
and both saved formats. It needs no Input, Generator, Executor runtime, or solver.

Real Lean/Blaster arithmetic controls verify passing and failing reports. The
four-component vesting command also ran with a 5,000 ms execution budget. All
five jobs remained INCONCLUSIVE, and the process returned exit code 2. That
short run supplies no passing result for vesting. The original 1,000,000-step
[120-second run](../VALIDATION.md) completed all five checks in 82.1 seconds and
returned zero with matching results. The history separately records the later
5,000,000-step checkpoint and its scope.
