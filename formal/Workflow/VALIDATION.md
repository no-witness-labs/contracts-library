# Validation history

## Experimental UP-012 vesting suite

The existing suite from PR #55 at `f5cbda7df624f2496dd2e6fe354a0cd15365b923`
completed all four jobs through the CLI: two signer-removal statements and two
applicability statements. All observations were Valid; Reporter emitted four
`PASS` rows and exit code zero. Execution took 64,283 ms under a 300,000 ms shared
budget: Types 1,799 ms, Tx 1,395 ms, and Checks 61,084 ms.

All three generated source files match the pinned candidate after only module
namespace/import replacement and embedding the supplied compiled script. The
propositions, typed data, transaction shapes, and 1,000,000-step bound remain
unchanged. The profile accepts only the original unparameterized vesting artifact.
Both supplied shapes have one signatory; the operation removes the first key.
General required-signer semantics remain a candidate-design question.

Generator fixture checks passed for the four propositions, provider selection,
unchanged UP-001 default, and explicit rejection of unsupported profiles.
Executor fixture checks also pass. These bounded observations retain Blaster's
SMT verification trust boundary and the original suite's model limits.

## Persistent output folders

The CLI now writes each run to its own `formal/output/run.XXXXXXXX/` directory.
The passing vault, failing vault, invalid-code, and timeout scenarios all retained
their expected 0/1/2 exit codes in separate output folders. Reports exist for all
four cases; executed plans also retain generated sources, logs, and `execution.json`.
Recorded module paths point into the actual output directory, and earlier runs
remain intact. Executor fixture checks also cover parent paths containing spaces,
distinct runs, retained source files, and a parent path that is a file.

## CLI delivery checks

The [quickstart](QUICKSTART.md) uses the compiled vault fixtures from PR #47 at
`0dde8ae76e3f8a239bf06685f72327aed4a7c3ef`, with their source and dependency
metadata preserved under `Workflow/Fixtures/`. The blueprint SHA-256 is
`afd375487a56be74f83f60e7c94fc2008f6e79b418a7bde3f1575bb4c6c9b426`.

The existing `lake exe universal` command produced these outcomes on the
prepared Linux toolchain:

| Scenario | Observed report | Exit code |
| --- | --- | --- |
| `vault.vault`, 120-second budget | Five `PASS` rows, each observed Valid | 0 |
| `vault_buggy.vault_buggy`, 120-second budget | Five `FAIL` rows, each observed Falsified | 1 |
| Invalid hexadecimal compiled code | `INCONCLUSIVE` before execution | 2 |
| `vault.vault`, one-millisecond budget | Five `INCONCLUSIVE` rows, execution budget exhausted | 2 |

The negative demo initially exposed a diagnostic-format bug: Blaster emits
counterexample fields with a leading space before `-`, which Executor treated
as unrelated errors. Commit `d582c8a` accepts that indentation while retaining
file, declaration, and source-position matching. The repeated negative run
returned the expected FAIL report. Regression checks cover indented values,
wrong positions, and values without a Falsified marker. Real arithmetic controls
now include a quantified counterexample; Executor and Reporter integrations pass.

These runs used Lean 4.24.0, Z3 4.15.2, the pinned dependencies, and the existing
5,000,000-step UP-001 scope. They used the installed tools directly in the prepared
checkout. This checkpoint did not rebuild the Aiken fixtures or validate installation
on a fresh machine. Raw reports, inputs, sources, and logs remain separate evidence
from the fixture source descriptions.

## Reviewed 5,000,000-step checkpoint

The owner approved a UP-001-only bound change after semantic review and five
individual experiments. The provider emits literal `5000000` while retaining
the raw redeemer domain, full per-purpose context, and negated-acceptance
predicate. The shared `ledgerFuel` helper remains 1,000,000 for other candidates.

The provider source SHA-256 for this checkpoint is
`c3a327075021bc07fbdec68a7f830f4adfe28b9f699f6247314219a4d79d398d`.
The compiled vesting artifact, toolchain, and dependency pins match the original
snapshot below.

### Individual proof experiments

Each purpose used a fresh workspace, one proof-compilation attempt, and a
120-second limit. Support compilation ran separately.

| Purpose | Result | Proof compilation |
| --- | --- | --- |
| Mint | Valid, exit 0 | 10.48 s |
| Withdraw | Valid, exit 0 | 11.32 s |
| Publish | Valid, exit 0 | 41.55 s |
| Vote | Valid, exit 0 | 13.80 s |
| Propose | Valid, exit 0 | 9.74 s |

The updated declaration fixture exactly matches these five experimental
statements. Scoped builds, Generator fixtures, and Input-to-Generator integration
on both the fixture and vesting blueprint passed. The integration harness only
type-checks propositions; it does not run solver proofs.

These observations retain the bounded non-acceptance meaning and Blaster's SMT
trust boundary. Fuel exhaustion satisfies the claim. Individual timings do not
establish a combined workflow time or a performance benchmark.

### Complete workflow at the reviewed bound

From `formal/`, with the pinned dependencies and tools prepared:

```sh
lake exe universal ../onchain/plutus.json linear_vesting.linear_vesting --check UP-001 --timeout-ms 120000
```

The updated workflow completed all five checks in **71,712 ms** under the
120,000 ms shared execution budget. Support compilation took 1,432 ms and the
Checks module took 70,277 ms. Reporter emitted five PASS rows and exit code zero.
All five observed results were Valid, and both execution metadata and report
rows recorded the 5,000,000-step scope. The generated declarations matched the
reviewed fixture; the source artifact and shared helpers remained unchanged.

This complete run is separate evidence from the individual experiments above.
It is one timing observation, without a performance guarantee or a claim that
the larger bound improves runtime. The default shared execution budget remains
30,000 ms; the example explicitly supplies 120,000 ms.

## Original 1,000,000-step baseline

The four-component prototype completed all five unparameterized UP-001
obligations for the linear-vesting blueprint in 82.1 seconds with a 120-second
shared execution budget. Reporter emitted five PASS rows and exit code zero.
No code, check statement, or CEK bound changed during this validation.

### Snapshot and scope

| Item | Value |
| --- | --- |
| Implementation | `d3bce414a3417b9227fa92f1e0a33672d2829749` |
| Candidate reference | `b44b6b0757a75d79b79a4de4712523ee3978760e` |
| Target | `linear_vesting.linear_vesting`, without parameters |
| Blueprint SHA-256 | `3d574b4f9c9e1d9998f96dd5ad27e000b2e2f244e8170f77af2bf02dcfdd8b0d` |
| Compiled-code SHA-256 | `29a7b3efd7c2064887a178696cf4ca76ad3ec63d66ca4ac848acae539638fd70` |
| Compiler recorded in blueprint | Aiken `v1.1.22+39d6b04` |
| Toolchain | Lean 4.24.0, Z3 4.15.2, and the pinned dependencies |
| Claim | No acceptance within `ledgerFuel` for each undeclared purpose |
| Bound | 1,000,000 CEK steps; fuel exhaustion satisfies the claim |

The artifact was an existing compiled snapshot, not a fresh Aiken rebuild.
Each result records Blaster's `blasterProven` warning: SMT verification without
a reconstructed proof term. The results support these compiled-model claims,
not general validator safety, source correspondence, or deployment assurance.

### Controlled single-obligation comparison

Both paths used the same mint-purpose theorem declaration, namespace, compiled
script, helper source, lockfile, and tools. Support modules compiled before
each fresh proof compilation, which had a 30-second limit.

| Path | Support compilation | Mint-purpose proof compilation | Result |
| --- | --- | --- | --- |
| Original candidate | 1.96 s | 9.09 s | Valid, exit 0 |
| Modular generator | 1.72 s | 9.20 s | Valid, exit 0 |

The observed timings are close. This single comparison gives no evidence of a
substantial single-obligation slowdown; it is not a performance benchmark.

### Complete workflow at the original revision

At implementation revision `d3bce414a3417b9227fa92f1e0a33672d2829749`, from
`formal/` with the pinned dependencies and tools prepared:

```sh
lake exe universal ../onchain/plutus.json linear_vesting.linear_vesting --check UP-001 --timeout-ms 120000
```

The recorded execution used 82,093 ms: 1,794 ms for support compilation and
80,295 ms for the five-obligation Checks module. All five observations were
Valid and matched their declared expectations.

Earlier 5- and 10-second executions remained inconclusive. A preliminary
30-second Checks-module probe also timed out. Those short budgets could not
complete this measured workload. The default remains 30,000 ms; use an explicit
larger budget for this example. One successful run does not guarantee its
runtime on another machine or run.

At this original checkpoint, the component fixtures, real Valid/Falsified
arithmetic controls, and all 54 legacy Python tests also passed. Those results
remain distinct from the vesting claim above. Each new execution retains its
own report, input snapshot, generated sources, raw logs, and `execution.json`
for review.
