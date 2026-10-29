# Run Plutus UPV

Plutus UPV (Universal Property Verifier) performs formal verification of
universal properties against compiled Plutus validators. The prototype accepts an existing Aiken-style Plutus V3 blueprint and one
unparameterized validator. It defaults to UP-001 and also offers the experimental
UP-012 vesting suite below. Each run produces a plain-text report, JSON report,
and exit code using ordinary Lean code and proof tools.

## Prepare once

Have Lean **4.24.0**, Z3 **4.15.2**, GNU coreutils (`timeout` and `mktemp`),
and Git on `PATH`.
From the repository root:

```sh
cd formal
lake build plutus-upv
export PATH="$PWD:$PATH"
```

The `PATH` command makes the repository launcher available as `plutus-upv` in
this shell. Alternatively, use `./plutus-upv` from `formal/`. The launcher prepares
the working directory and resolves relative blueprint paths from your calling
directory. CLI validation uses the installed tools on Linux. No global installation
or shell configuration edit is required.

The first build can download dependencies and compile them. Lake uses the
revisions in the committed `lake-manifest.json`; reserve `lake update` for an
intentional dependency upgrade. The launcher also builds the command when needed. From `formal/`,
`lake exe plutus-upv ...` is equivalent. The legacy
`lake exe universal BLUEPRINT VALIDATOR ...` entry point remains available.

## Run the passing example

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json vault.vault --check UP-001 --timeout-ms 120000
```

The command reads and validates the blueprint, generates five checks for
undeclared purposes, runs Lean/Blaster, and reports the result. It is quiet while the
checks run. Wait for the final summary:

```text
Summary: 5 PASS, 0 FAIL, 0 INCONCLUSIVE
Overall: PASS (exit 0)
Evidence: /path/to/repo/formal/output/run.XXXXXXXX
Report: /path/to/repo/formal/output/run.XXXXXXXX/report.json
```

Each run creates a separate folder under `formal/output/`:

```text
output/run.XXXXXXXX/
├── report.txt
├── report.json
├── input.json
├── execution.json
└── Generated/Workflow/
    ├── Types.lean
    ├── Checks.lean
    └── compiler outputs and logs
```

Earlier runs remain in their own folders. Input errors can produce report files
without generated sources or execution artifacts. The output folder is local
and excluded from Git.

For supporting definitions such as `EveryMint` and `EveryWithdraw`, use the
[check file map](CHECK-FILES.md). Those definitions live in shared repository
code that the generated checks import.

## Check the other outcomes

The deliberately failing validator uses the same blueprint:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json vault_buggy.vault_buggy --check UP-001 --timeout-ms 120000
```

An invalid compiled artifact exercises input rejection:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/invalid-code.json invalid.invalid --check UP-001 --timeout-ms 120000
```

A one-millisecond execution budget exercises timeout handling:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json vault.vault --check UP-001 --timeout-ms 1
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
plutus-upv run /absolute/path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
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
`plutus-upv --help` for the supported arguments.

## Test the UP-012 candidate

For the existing vesting suite:

```sh
plutus-upv run Workflow/Tests/UP012/Inputs/plutus.json linear_vesting.linear_vesting --check UP-012 --timeout-ms 300000
```

This experimental profile runs four original checks: signer removal for Claim
and Cancel, plus an applicability check for each. It uses the candidate's
1,000,000-step bound and supplied one-signer shapes. The command accepts only
the pinned vesting artifact; other validators return INCONCLUSIVE/2. The
[UP-012 test guide](Tests/UP012/README.md) describes its scope and restrictions.

## Test the tool

```sh
plutus-upv test
```

This command builds the explicit workflow test targets and runs every suite
sequentially: component units, runner failure controls, component integrations,
and the UP001/UP012 scenarios. Verbose output includes commands, case starts,
stdout/stderr, durations, and evidence paths. The runner retains logs and a
summary in a fresh ignored `formal/output/test.XXXXXXXX/` directory. Individual
validator runs retain their generated sources and raw compiler/solver logs.

Intentional FAIL and INCONCLUSIVE cases verify that the workflow detects bad
validators, rejects unsupported or malformed inputs, and respects deadlines.
They count as successful tests when their assertions match. The test command
returns zero only when all required suites ran and passed. It continues with
independent suites after a test failure, but stops on a build failure so stale
executables cannot produce a false success.

The [test index](Tests/README.md) lists individual commands for focused debugging.
UP-012 retains its fixed vesting scope and includes the intentional signer-identity
negative control; changing that property definition remains separate work.
