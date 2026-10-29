# Run the prototype from the CLI

The prototype accepts an existing Aiken-style Plutus V3 blueprint and one
unparameterized validator. It runs UP-001 and produces a plain-text report,
JSON report, and exit code. The runtime uses ordinary Lean code and proof tools.

## Prepare once

Have Lean **4.24.0**, Z3 **4.15.2**, GNU `timeout`, and Git on `PATH`.
From the repository root:

```sh
cd formal
lake build universal
```

Keep subsequent commands in `formal/`, where `lean-toolchain` and `lakefile.toml`
live. CLI validation used these tools on Linux.

The first build can download dependencies and compile them. Lake uses the
revisions in the committed `lake-manifest.json`; reserve `lake update` for an
intentional dependency upgrade. `lake exe` also builds the command when needed.

## Run the passing example

```sh
lake exe universal Workflow/Fixtures/plutus.json vault.vault --check UP-001 --timeout-ms 120000
```

The command reads and validates the blueprint, generates five checks for
undeclared purposes, runs Lean/Blaster, and reports the result. It is quiet while the
checks run. Wait for the final summary:

```text
Summary: 5 PASS, 0 FAIL, 0 INCONCLUSIVE
Overall: PASS (exit 0)
Evidence: /tmp/...
Report: /tmp/.../report.json
```

The printed directory contains `report.txt`, `report.json`, and, for executed
checks, the input snapshot, generated sources, logs, and `execution.json`.
Input errors can produce report files without execution artifacts. Copy the
printed directory to a permanent location if you need to retain the evidence.

## Check the other outcomes

The deliberately failing validator uses the same blueprint:

```sh
lake exe universal Workflow/Fixtures/plutus.json vault_buggy.vault_buggy --check UP-001 --timeout-ms 120000
```

An invalid compiled artifact exercises input rejection:

```sh
lake exe universal Workflow/Fixtures/invalid-code.json invalid.invalid --check UP-001 --timeout-ms 120000
```

A one-millisecond execution budget exercises timeout handling:

```sh
lake exe universal Workflow/Fixtures/plutus.json vault.vault --check UP-001 --timeout-ms 1
```

| Example | Expected summary | Exit code |
| --- | --- | --- |
| Passing vault | Five PASS rows | 0 |
| Deliberately failing vault | Five FAIL rows | 1 |
| Invalid artifact | INCONCLUSIVE with an input-error reason | 2 |
| Tiny execution budget | Five INCONCLUSIVE rows | 2 |

Run `echo $?` immediately after a command to inspect its exit code. The deliberate
failure and error cases return nonzero codes as part of the demo.

## Use your blueprint

```sh
lake exe universal /absolute/path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
```

Select the `module.validator` part of the blueprint's handler titles. The first
provider supports validators without parameters; Input preserves parameter
metadata, but Generator does not yet handle nonempty parameter lists.

The default execution budget is 30 seconds. The examples request 120 seconds;
this budget covers generated-module execution, while setup and reporting add
overhead. It is separate from UP-001's 5,000,000 CEK-step model bound.

UP-001 checks non-acceptance for undeclared purposes within that bound. Fuel
exhaustion satisfies the claim, and results inherit Blaster's SMT trust boundary.
See the [validation history](VALIDATION.md) for measured runs and limits, or
`lake exe universal --help` for the supported arguments.
