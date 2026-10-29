# Run candidate checks

## Modular prototype

Start with the [CLI quickstart](../Workflow/QUICKSTART.md) for setup, demo
validators, expected exit codes, and report locations.

From `formal/`, with the pinned dependencies and tools prepared:

```sh
lake exe universal /path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
```

The four-component prototype writes a plain-text summary and JSON report and
returns 0 for PASS, 1 for FAIL, or 2 for INCONCLUSIVE. Its first provider supports
unparameterized UP-001 targets. It does not apply waivers yet. See the
[Reporter guide](../Workflow/Reporter/README.md) for the command, evidence, and
limits, and the [workflow design](../Workflow/README.md) for component boundaries.

## Python reference prototype

Use a pinned checkout with the selected candidate generator integrated, the
repository's Lean/Z3 versions installed, and clean dependency checkouts at the
revisions in `lake-manifest.json`. A missing generator or dependency gives exit 2.
The runner supports `otherPurpose` (UP-001), `malformedRedeemer` (UP-005), and
`returnDatum` (UP-006). It does not add these generators to a checkout.

From `formal/`, point at an existing Plutus V3 blueprint:

```sh
python3 -I scripts/universal.py /path/to/plutus.json module.validator --check otherPurpose
```

The default 30-second budget covers preparation, builds, and checking together.
Use `--timeout SECONDS` to choose another budget. A timeout stops the command's
process group; it does not establish failure of the property.
The runner invokes neither Aiken nor `lake update`.

Each run saves its blueprint, runner, generator, compiled code, generated sources, logs,
and `report.json` under `.lake/universal/run-*/`. It records input/source hashes,
tool versions, raw evidence, and the interpreted results. Generated modules use a
fresh temporary namespace; their temporary sources and module caches are removed
afterward. Existing authored files and `Scripts/` stay untouched.

| Result | Meaning |
| --- | --- |
| `PASS` | The required result and any applicability evidence are established |
| `FAIL` | The result contradicts the check's expectation |
| `NOT_APPLICABLE` | Applicability is disproved within the checked scope |
| `INCONCLUSIVE` | Error, timeout, or missing evidence |

Expectations belong to the check implementation. A counterexample to a negated
existence claim can be a successful witness. An empty set of obligations, silent
process completion, and unknown applicability never count as a pass.
Counterexamples remain in the logs.
These results inherit the check's scope and Blaster's `blasterProven` trust boundary.

## Reviewed exceptions

Optional `universal.json`, or `--config FILE`, contains waivers. Use the canonical
validator name and exact theorem name printed in the report:

```json
{
  "module.validator": {
    "returnDatum": {
      "blueprint_sha256": "<64 lowercase hex digits from report.json>",
      "reason": "<reviewed reason>",
      "owner": "<reviewer>",
      "until": "YYYY-MM-DD"
    }
  }
}
```

All four fields are required. The waiver matches the entire blueprint file,
including its schemas; any byte change invalidates it. It remains valid through
the stated UTC date. A waiver accepts only `FAIL` or `NOT_APPLICABLE`, preserving
the original label with `(waived)`. It cannot waive errors or missing evidence.

Exit `0` means every requested check passes or has a valid waiver; `1` means an
unwaived failure; `2` means an execution problem, inconclusive result, or unreviewed
inapplicability. Code `2` takes precedence; all results remain in the report.
Runner success does not replace proof-build acceptance. Hosted CI is separate.

Run the stdlib tests from the repository root:

```sh
python3 -I -B -m unittest discover -s formal/tests -p 'test_universal.py'
```

The tests use synthetic process output for orchestration; they do not prove
validator properties. A real check also requires its integrated generator.
