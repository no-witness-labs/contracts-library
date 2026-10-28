# Validation baseline

The four-component prototype completed all five unparameterized UP-001
obligations for the linear-vesting blueprint in 82.1 seconds with a 120-second
shared execution budget. Reporter emitted five PASS rows and exit code zero.
No code, check statement, or CEK bound changed during this validation.

## Snapshot and scope

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

## Controlled single-obligation comparison

Both paths used the same mint-purpose theorem declaration, namespace, compiled
script, helper source, lockfile, and tools. Support modules compiled before
each fresh proof compilation, which had a 30-second limit.

| Path | Support compilation | Mint-purpose proof compilation | Result |
| --- | --- | --- | --- |
| Original candidate | 1.96 s | 9.09 s | Valid, exit 0 |
| Modular generator | 1.72 s | 9.20 s | Valid, exit 0 |

The observed timings are close. This single comparison gives no evidence of a
substantial single-obligation slowdown; it is not a performance benchmark.

## Complete workflow

From `formal/`, with the pinned dependencies and tools prepared:

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

The component fixtures, real Valid/Falsified arithmetic controls, and all 54
legacy Python tests also pass. These results remain distinct from the vesting
claim above. Each new execution retains its own report, input snapshot,
generated sources, raw logs, and `execution.json` for review.
