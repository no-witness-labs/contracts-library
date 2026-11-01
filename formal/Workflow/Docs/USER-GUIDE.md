# Run Plutus UPV

Plutus UPV (Universal Property Verifier) checks universal properties against
compiled Plutus validators using Lean and configured proof tools. The prototype
accepts the documented Aiken-style Plutus V3 blueprint profile. By default, one
command processes all logical validators and all nine registered property/model
combinations. They comprise six for UP-001, two for UP-012, and one for UP-015. These are
experimental workflow bindings; registration does not establish general readiness
of the properties or models.

The app prints a terminal summary and retains local run files. The separate
human-friendly final report remains future work in
[issue #83](https://github.com/no-witness-labs/contracts-library/issues/83).

## Prepare once

Have Lean **4.24.0**, Z3 **4.15.2**, GNU coreutils (`timeout`, `mktemp`,
`date`, and `sha256sum`), and Git on `PATH`. From the repository root:

```sh
./formal/install.sh
```

The installer builds the app and links `~/.local/bin/plutus-upv` to this checkout.
Keep the checkout in place: it supplies the app, metadata, and Lean dependencies.
If that bin directory is outside your `PATH`, the installer prints the shell
command to add it. It does not edit shell configuration. Use `--bin-dir DIRECTORY`
to choose another location. Repeating the installation for the same checkout is
safe; the installer refuses to replace an unrelated existing command.

You can also use `./plutus-upv` directly from `formal/`. The launcher resolves
input and selection-file paths from your calling directory, then uses the app's
Lean environment. From `formal/`, `lake exe plutus-upv ...` also works.

The first build can download and compile dependencies. Lake uses revisions in
the committed `lake-manifest.json`; reserve `lake update` for intentional upgrades.
The launcher also builds the command when needed.

## Run and select work

From a directory containing `plutus.json`, run:

```sh
plutus-upv run
```

The default timeout is **5 minutes per validator/check combination**. Input
defaults also work with selection flags, for example `plutus-upv run --check UP-001`.
Run files remain under this app checkout's `formal/output/`; the terminal prints
their location. The command leaves the input project unchanged.

Run all validators and registered combinations:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json --timeout-ms 120000
```

Select one validator and one property:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json --validator vault.vault --check UP-001 --timeout-ms 120000
```

The earlier positional form also works:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json vault.vault --check UP-001 --timeout-ms 120000
```

`--validator` and `--check` may repeat. Use the full `module.validator` name or an
unambiguous short name. Entries for several handlers form one logical target.
Selection preserves blueprint/catalogue order and runs each combination once.
The app captures the blueprint once and prepares each selected validator once.
A malformed compiled artifact produces that validator's preparation error while
other validators continue. Invalid shared JSON/title structure stops discovery.

## Select properties with a file

Start with [checks.example.json](../../checks.example.json), which enables all three
registered properties, or save your own `checks.json`. For example, enable only UP-001:

```json
{
  "UP-001": true,
  "UP-012": false,
  "UP-015": false
}
```

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json --checks-file checks.json
```

Without a file or `--check`, all registered properties run. With a file, only
properties explicitly set to `true` run; `false` and omitted properties stay off.
Each enabled property selects all its registered model combinations. Clients do
not supply transaction models.

Unknown IDs, nonboolean values, and malformed files fail before verification.
Do not combine `--check` with `--checks-file`. An empty enabled set is a valid
no-op: the terminal says that verification did not run, and no check results
claim a pass.

## Read the terminal and run files

The terminal table shows PASS, FAIL, and INCONCLUSIVE counts per validator.
Each count represents one property/version/model combination; supporting
applicability obligations do not add extra checks. The app also prints recorded
check counts, elapsed time, errors, and output paths. Open the printed `Review`
path (`README.md`) to browse relative links to generated Lean, check results,
logs, and shared source snapshots. `Index` points to the machine-readable
`run.json`. The app assigns no overall verification verdict.

Each invocation creates a fresh local folder:

```text
output/run.<timestamp>.<unique-id>/
├── README.md
├── run.json
├── sources/
│   ├── index.json
│   ├── Formal/                          # imported project Lean sources and compiled modules
│   ├── _logs/                           # supporting-source compilation
│   ├── lean-toolchain
│   ├── lake-manifest.json
│   └── lakefile.toml
├── input.json
├── checks.json                         # when a selection file was supplied
└── validators/
    └── vault.vault/
        └── UP-001-v1-TxM-001/
            ├── check-result.json
            ├── input.json
            ├── execution.json
            └── Generated/
                ├── Types.lean
                ├── Checks.lean
                └── compiler outputs and logs
```

Earlier runs remain intact, and Git ignores the output. Folder names encode
characters such as `/`; `run.json` preserves canonical validator names.

| File | Contents |
| --- | --- |
| Root `README.md` | Relative links to retained files and recorded results; refreshed at each checkpoint |
| `sources/` | Shared imported project sources, compiled modules, source-compilation logs, and environment records |
| `sources/index.json` | Source hashes, imports, compilation state, toolchain/configuration hashes, and dependency revision/dirty-state records |
| `run.json` | Invocation/options, selected work, result-file references, errors, elapsed time, and completion marker; updated as work progresses |
| Root `input.json` | Captured readable blueprint, including input that later fails validation |
| Root `checks.json` | Supplied selection-file snapshot, when present |
| Per-check `check-result.json` | The assessed six-field result, including scope, reasons, and evidence references |
| Per-check `input.json` | The same captured blueprint used to prepare that validator |
| Per-check `execution.json` | Attempted commands, timing, raw observations, and diagnostics |
| `Generated/` | Generated Lean, stdout/stderr logs, and successful compiled modules; UP-012 and UP-015 also generate `Tx.lean` |

An interrupted run can leave its last saved index unfinished. Files depend on how
far an attempt progressed: unreadable input has no snapshot, and validator
preparation errors have no generated proof files.

The app captures and compiles supporting project definitions such as `EveryMint`
and `EveryWithdraw`, including their transitive project imports, once per run as
needed. Generated checks use those captured modules. External libraries still
use the installed Lean environment. The records include their configured pins,
actual checkout revisions, and tracked dirty state. Dependency sources and the
runtime remain outside the bundle.

Independent replay remains future work. See the
[check file map](DEVELOPER-GUIDE.md#generated-goals-and-supporting-files).
The navigation README is separate from the future final client report. The new
command does not generate legacy `report.json`/`report.txt` files.

## Time limits and exit codes

The default execution limit is 5 minutes **per validator/check combination**.
`--timeout-ms 120000` gives each combination up to 120 seconds across its generated
modules. Supporting-source preparation has a separate compilation budget of the
greater of the selected timeout and 30 seconds. It does not consume the proof
budget. Setup and file retention add overhead. These limits are separate from
the property's CEK-step bound.

Individual failures, unsupported checks, and timeouts
retain their outcomes while independent checks continue. A supporting-source
capture or compilation failure retains available generated sources, source logs,
and the source index, records INCONCLUSIVE, and counts as an app operational error.
Because the source bundle is shared, a preparation failure prevents later generated
checks from executing in that run. Their generated files and explained INCONCLUSIVE
results are still retained; start a fresh run after correcting the source problem.

| Product exit | Meaning |
| --- | --- |
| `0` | The app completed and retained the selected work, including ordinary FAIL or INCONCLUSIVE outcomes |
| `2` | Input, validator preparation, catalogue, app, or storage errors prevented normal completion/retention |

A zero exit code does not assert that properties passed; inspect the table and
result files. The legacy `lake exe universal BLUEPRINT VALIDATOR ...` command
retains verdict-based `0`/`1`/`2` exits and its earlier report files.

## Property scope and examples

UP-001 checks nonacceptance for undeclared purposes within **5,000,000 CEK steps**.
A selected combination for an already declared purpose has no obligations and
returns INCONCLUSIVE with an explanation. Fuel exhaustion satisfies this bounded
claim; it does not establish explicit rejection. Current adapters support
absent/empty parameters; Input preserves nonempty descriptions without applying
values.

The failing validator and invalid artifact exercise other outcomes:

```sh
plutus-upv run Workflow/Tests/UP001/Inputs/plutus.json vault_buggy.vault_buggy --check UP-001 --timeout-ms 120000
plutus-upv run Workflow/Tests/UP001/Inputs/invalid-code.json invalid.invalid --check UP-001
```

Run the experimental vesting profile with:

```sh
plutus-upv run Workflow/Tests/UP012/Inputs/plutus.json linear_vesting.linear_vesting --check UP-012 --timeout-ms 300000
```

UP-012 has two registered combinations, Claim and Cancel. Each contains a property
and linked applicability obligation. They use the **1,000,000-step** bound and
fixed one-signer models, and accept only the pinned vesting artifact. Other targets
produce explained INCONCLUSIVE outcomes. Its intended universal meaning remains
separate work in [issue #33](https://github.com/no-witness-labs/contracts-library/issues/33).

UP-015 uses the same validator input and native Claim model, TxM-007:

```sh
plutus-upv run Workflow/Tests/UP012/Inputs/plutus.json linear_vesting.linear_vesting --check UP-015 --timeout-ms 300000
```

Its single combination checks acceptance after reversing the two Claim outputs
within 1,000,000 CEK steps. Linked applicability requires a valid accepted original,
a valid reversal, and an output list that changes. The vesting profiles share
the pinned artifact guard and model preparation. This supplies no general
output-permutation model. See the
[UP-015 scenario](../Tests/UP015/README.md).

The three scenarios test workflow behavior. They do not establish general
property or model readiness. Definition work remains open in
[UP-001 #23](https://github.com/no-witness-labs/contracts-library/issues/23),
[UP-012 #33](https://github.com/no-witness-labs/contracts-library/issues/33), and
[UP-015 #36](https://github.com/no-witness-labs/contracts-library/issues/36).
[Model authoring #89](https://github.com/no-witness-labs/contracts-library/issues/89)
and [candidate integration #96](https://github.com/no-witness-labs/contracts-library/issues/96)
remain separate work.

Solver results inherit Blaster's SMT trust boundary. Model validity, ledger
reachability, source correspondence, and protocol relevance remain separate
questions. See [validation history](VALIDATION.md) for earlier measured runs and
the [UP-012 guide](../Tests/UP012/README.md) for its restrictions.

## Test the tool

```sh
plutus-upv test
```

The command builds the test targets and runs all workflow suites with verbose
commands, case starts, stdout/stderr, durations, and evidence paths. It retains
logs and summaries in a fresh ignored `output/test.XXXXXXXX/` directory.

Intentional FAIL and INCONCLUSIVE cases count as successful tests when their
assertions match. The test command returns zero only when all required suites
ran and passed. Independent suites continue after a test failure; a build failure
stops execution so stale binaries cannot produce a false success. The
[test index](../Tests/README.md) lists focused commands and legacy scenario tests.
