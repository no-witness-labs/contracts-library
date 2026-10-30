# Reporter component

Reporter compares Executor observations with the jobs' declared expectations.
It produces a plain-text summary, a small JSON report, and an exit code. This
first version has no branding, rich layouts, expanded narrative, or waiver
handling.

## Outcomes

| Status | Meaning | Exit code |
| --- | --- | --- |
| PASS | All jobs have trustworthy results, required applicability holds, and expectations match | 0 |
| FAIL | At least one trustworthy, qualified property result differs from its expectation | 1 |
| INCONCLUSIVE | No qualified failure exists, but a result or prerequisite is incomplete, or no jobs ran | 2 |

An expected Falsified property result can produce PASS. Reporter uses explicit
job roles and applicability references rather than property-specific rules.
Qualified failures take precedence over incomplete results in the overall
status. Each incomplete row and its reason remain visible. Summary counts include
all obligation rows, including applicability; they are not a property coverage count.

Statuses apply to the stated check scope. A report does not establish general
validator safety. The JSON retains each job's expected and observed result,
scope, issues, and a reference to Executor's detailed evidence.

## Qualification and partial results

A Valid solver observation concerns the formal statement within its stated
model and execution semantics. It does not establish that the statement is an intended
requirement of the protocol. Likewise, the applicability obligations below
establish the existence of modeled scenarios, not their business relevance.

Each property job can reference one applicability obligation by module and name.
The reference must resolve to a unique applicability job for the same property,
with a Valid expectation and no prerequisite of its own. An ordinary property
without a reference needs no applicability obligation.

| Applicability observation | Applicability row | Linked property |
| --- | --- | --- |
| Trustworthy Valid | PASS | Compare its trustworthy result with its expectation |
| Trustworthy Falsified | INCONCLUSIVE: no applicable scenario in this model | INCONCLUSIVE |
| Unknown, missing, interrupted, or untrustworthy | INCONCLUSIVE: applicability not established | INCONCLUSIVE |

Keep raw property and applicability observations even when qualification fails.
A property proof can therefore retain raw Valid or Falsified while its reported
status is INCONCLUSIVE. An invalid reference also leaves its property inconclusive.
The workflow validates the declared links; the definition author remains
responsible for their mathematical relevance.

Executor marks an observation `evidenceComplete` only after its process finishes
without module-wide diagnostic or protocol problems. Exit 1 can still carry a
trustworthy Falsified observation. Reporter also requires a unique observation,
matching metadata, no local issues, and a conclusive result.

Independent trustworthy results retain PASS/FAIL when another check times out
or fails. Partial output from a stopped process remains INCONCLUSIVE. Global
plan or attribution corruption invalidates the affected run conservatively.
The completion marker relies on the existing independent generated-obligation
discipline; it does not certify arbitrary dependencies between proof declarations.

## Planned metadata and run configuration

Workflow reports now retain the selected property-definition snapshot, including
its definition version, explanations, and stated limits. Executor retains the
same snapshot in its manifest; a mismatch makes the report inconclusive. See the
[workflow metadata guide](../METADATA.md). Model metadata and combined-check
records remain design work in [issue #65](https://github.com/no-witness-labs/contracts-library/issues/65).
Clients can review protocol relevance afterward. Multiple variants and optional
enable/disable controls remain later work; current reports retain all job rows.

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
lake exe plutus-upv run /path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
```

The thin `Workflow.Main` entry point connects Input, Generator, Executor, and
Reporter. The application supplies the candidate resolver through its composition index;
the default remains UP-001. The first provider supports unparameterized
UP-001 targets. The command requires the prepared `LEAN_PATH` supplied by
`lake exe` and performs no dependency installation.
`--check UP-012` selects the experimental pinned vesting suite, including its
two signer-removal and two applicability statements.

The default execution budget is 30,000 ms. The option controls Executor's shared
module budget; package builds, input reading, generation, and reporting add
overhead. The command prints the summary and JSON path, saves both report
formats, and preserves the input snapshot. It writes an inconclusive report for
input, provider-selection, and preparation errors too.

The CLI saves each run under `formal/output/run.XXXXXXXX/` and prints its exact
path. Earlier run directories remain intact. Input errors have report files
without generated Lean sources; executed jobs also retain sources, compiler
outputs, logs, and `execution.json`.

Reviewed exceptions and `universal.json` waiver handling remain future work.
Unknown options return an inconclusive usage error. Standalone CBOR, additional
properties, typed parameter generation, and portable packaging remain later
work.

## Tests

The component harnesses live under `Workflow/Tests/Unit/Reporter/` and share
the arithmetic controls in `Workflow/Tests/Unit/Fixtures/`.


From `formal/`:

```sh
lake build Workflow workflow_reporter_tests workflow_reporter_integration universal
lake exe workflow_reporter_tests
lake exe workflow_reporter_integration
```

The isolated unit harness checks explicit applicability references, separate
action groups, incomplete evidence, metadata mismatches, and failure precedence.
It also covers missing/duplicate jobs, corrupted plans, expected counterexamples,
raw-result retention, per-row explanations, the successful summary fixture, and
both saved formats. It needs no Input, Generator, Executor runtime, or solver.

Real Lean/Blaster arithmetic controls verify passing and failing reports. A
further control proves that a Falsified applicability result leaves both the
support row and a linked Valid property INCONCLUSIVE, retaining their raw results.
The four-component vesting command also ran with a 5,000 ms execution budget. All
five jobs remained INCONCLUSIVE, and the process returned exit code 2. That
short run supplies no passing result for vesting. The original 1,000,000-step
[120-second run](../VALIDATION.md) completed all five checks in 82.1 seconds and
returned zero with matching results. The history separately records the later
5,000,000-step checkpoint and its scope.
