# Blueprint type and CBOR extraction

For bounded candidate runs and result reporting, see [Run candidate checks](WORKFLOW.md).

This foundation extracts the type-generation pass from
[sayyadirfanali's work in PR #44](https://github.com/no-witness-labs/contracts-library/pull/44)
at `99a5734f0e036b6abfb4c3f121a298e35fa2eff6`.
It does not generate property statements or transaction shapes.

From `formal/`, using a chosen blueprint snapshot:

```sh
python3 -I scripts/process_blueprint.py ../onchain/plutus.json linear_vesting --cbor-only
python3 -I scripts/process_blueprint.py ../onchain/plutus.json linear_vesting --out Formal/Vesting/Linear/Blueprint
```

The first command copies the blueprint's compiled hex to
`Scripts/linear_vesting.linear_vesting.cbor`.
The second writes only `Types.lean`: types, `IsData` instances, script arguments,
the imported program, and bounded acceptance/rejection predicates.
Existing transaction and check files are not replaced or deleted.
Use `module.validator` when a short validator name is ambiguous.

With the existing pinned Lean dependencies available, compile the new modules:

```sh
lake build Formal.Universal.Properties Formal.Vesting.Linear.Blueprint.Types
```

No automatic Aiken rebuild or dependency update occurs.
Type generation supports Plutus V3; recursive schema definitions fall back to
`Data` with a warning.
The copied bytes and recorded blueprint hash are not independently validated
for provenance or CBOR correctness.
CEK fuel is a step bound, not a Cardano CPU or memory budget.

Run the stdlib-only Python tests from the repository root:

```sh
python3 -I -B -m unittest discover -s formal/tests -p 'test_process_blueprint.py'
```

The synthetic fixture is not an executable validator.
Python tests check translation and file behavior, not Lean compilation or proof validity.
