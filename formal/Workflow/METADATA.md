# Workflow property-definition metadata

Plutus UPV reads the registered property's description from
[`Candidates/property-definitions.json`](../Candidates/property-definitions.json).
The workflow-scoped [JSON Schema](property-definition.schema.json) describes
the agreed layout:

| Group | Contents |
| --- | --- |
| Identity | ID, definition version, title, category |
| Explanation | Summary, precise claim, purpose |
| Scope | Relevance conditions, logical premises, limitations |
| Formalization | Primary maintained declaration and static theorem/lemma names |
| References | Supporting code and documents using label/target pairs |

`schema_version` identifies the metadata format. The registered definitions
currently use format 2 and definition version 1. Model metadata and combined
check schemas remain separate design work in issue #65.

## Shape and binding

The schema and [Lean reader](PropertyDefinition.lean) check types and known
fields. They preserve missing fields, supplied empty values, and empty lists.
They reject wrong types, explicit nulls, and unknown fields. Required/optional
and list-cardinality policy remain open; structural validity alone does not
make a record runnable or establish a theorem.

The application catalogue binds a selected record to an existing registered
provider by property ID and definition version. A selected record must resolve
uniquely. Its primary declaration, when supplied, must match the registration.
These association checks prevent metadata from relabeling another implementation;
they do not make every descriptive field mandatory. Unregistered or malformed
metadata produces a preparation error rather than selecting alternative code.

Metadata references are descriptive. The workflow does not import, evaluate,
fetch, or execute code from them. The registered Lean implementation continues
to determine the propositions, model, expectations, applicability relationships,
and CEK bounds. Protocol relevance remains a client interpretation.

## Evidence and reports

The catalogue loads the selected record once. Generator passes that snapshot
to Executor and Reporter. `execution.json` and `report.json` include it as
`propertyDefinition`; the text report shows supplied fields with plain labels.
Absent metadata stays absent; no default descriptions or assurances are invented.
If the plan and execution snapshots differ, Reporter treats that as an integrity
problem and keeps the affected result inconclusive.

Known metadata remains in input, generation, and execution-preparation error
reports. Metadata errors themselves do not claim a failed validator property.
If both intake and catalogue lookup fail, intake keeps its existing precedence.
The original readable-input capture gap on intake failures remains separate work.

Static theorem names in metadata are not results for the supplied target.
The current UP001/UP012 records list no static target proofs: their target-specific
theorems are generated during execution. Generated sources, observations, and
the precise executed scope remain in each run's evidence. Metadata prose does
not strengthen that evidence or prove correspondence to ledger execution.
This checkpoint does not add full source/dependency fingerprinting; that remains
separate evidence work.

## Workflow-first rollout

This adoption covers only the two registered workflow definitions. UP-012 remains
the pinned vesting integration example; its metadata describes that limitation
without redesigning the property or its transaction model.

The shared schemas under `docs/property-catalogue/`, the U-* theorem catalogue,
and other branches remain unchanged. [Issue #66](https://github.com/no-witness-labs/contracts-library/issues/66)
stays open for the broader migration and reconciliation across existing PRs.
The workflow implementation PR references that issue without closing it.

Run the focused metadata checks from `formal/`:

```sh
lake exe workflow_metadata_tests
```

`./plutus-upv test` includes them with the other workflow suites.
