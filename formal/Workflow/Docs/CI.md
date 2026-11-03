# Fast formal CI

The fast checkpoint builds the Plutus UPV CLI and runs ten existing unit and
parity suites. Its explicit targets avoid the default `Formal` build, which
includes contract proofs.

From the repository root of a prepared checkout:

```sh
bash formal/scripts/ci-fast.sh
```

Use the Lean version in `formal/lean-toolchain`, Z3 4.15.2, and the dependency
revisions in `formal/lake-manifest.json`. CI setup supplies those tools without
Nix. The script uses Bash, GNU `timeout`, `date`, `readlink`, `mktemp`, and
`tee`, as available on the Linux runner.

## Coverage and outcome

| Suite | Coverage |
| --- | --- |
| Input | Blueprint parsing, selection, and input errors |
| Generator | Generic plan construction and validation |
| Preparation | Input compatibility, compiled-program decoding, and hashes |
| Metadata | Property/model records and binding checks |
| Selection | Validator and property selection rules |
| Discovery | Selected-source isolation, startup errors, deadlines, and process cleanup |
| Runner controls | Expected negative controls, unexpected failures, and retained logs |
| UP-001 property unit tests | Purpose selection, goal parity, and model bindings |
| UP-012 property unit tests | Goal parity, model-list registration, and reviewed limitations |
| UP-015 property unit tests | Goal/applicability parity and reviewed limitations |

UP-015 runs explicitly with `--unit`. These suites perform local computations,
kernel equivalence checks, and controlled test-process runs; they do not execute
the full validator SMT scenarios.

A failed build stops the run before any possibly stale executable is used.
After a successful build, all ten independent suites are attempted. A nonzero
test exit or a failure to retain its streamed log makes the fast command fail.
Printed `FAIL` or `INCONCLUSIVE` inside an expected control does not determine
the CI outcome.

The build has a 20-minute limit; each suite has a two-minute limit. The hosted
job also has its own overall limit. A timeout is a failed CI command, not a
property counterexample.

## Retained evidence

Every invocation creates `formal/output/ci-fast.XXXXXXXX/` with a streamed log
for each attempted step, `summary.tsv`, `summary.md`, and copies of the
toolchain and dependency manifests. Each log retains both stdout and stderr.
The summaries record command exits, log-write exits, and elapsed time.
When `GITHUB_STEP_SUMMARY` is available, the command appends its result there.

The hosted workflow runs on pull requests and pushes targeting `main` or
`fv/m1.1-foundation`, and supports manual dispatch. It uses Ubuntu 24.04,
read-only repository permissions, the checked-in Lean toolchain, and the
checksum-verified official Z3 4.15.2 archive. Action revisions are pinned.
The 30-minute job uploads `formal/output/` on success or failure, including
structured control evidence, and retains the artifact for 14 days. The build
cache is keyed by runner architecture, workflow, toolchain, and dependency
manifest; source changes still pass through Lake's incremental rebuild checks.

The full `./plutus-upv test` command and real validator runs remain separate
validation steps. A successful fast checkpoint establishes the listed regression
checks, not a proof result for a validator. The unfinished UP-009/UP-016 proof
attempts are outside this target set.

