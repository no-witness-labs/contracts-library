# Run Plutus UPV

Plutus UPV is the Universal Property Verifier for compiled Plutus validators.
Use the Lean CLI with the installed tools. The [quickstart](../Workflow/QUICKSTART.md)
covers setup, demo validators, expected exit codes, and output locations.

From `formal/`:

```sh
./plutus-upv run /path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
./plutus-upv test
```

UP-001 supports unparameterized Plutus V3 validators. The experimental UP-012
provider runs the original pinned vesting suite; its command and restrictions
are in the quickstart.

Each run creates a local `formal/output/run.XXXXXXXX/` folder containing reports
and, after generation, Lean sources and execution evidence. Git ignores that
folder. The small committed fixtures provide repeatable test inputs and expected
declarations.

The CLI returns 0 for PASS, 1 for FAIL, and 2 for INCONCLUSIVE. Results retain the
selected check's model, bound, and Blaster trust boundary. Waiver handling,
UP-005/UP-006 integration, and other providers remain future work.

The `test` command runs every workflow suite with verbose logs. Its exit code
describes whether the tests passed, including their intentional FAIL/timeout
cases. The legacy `lake exe universal ...` entry point remains available.

See the [Reporter guide](../Workflow/Reporter/README.md) for outcome semantics,
the [file map](../Workflow/CHECK-FILES.md) for supporting definitions, and the
[workflow design](../Workflow/README.md) for component boundaries.
