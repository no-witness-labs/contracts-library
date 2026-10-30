# Workflow metadata

Workflow metadata describes property definitions, transaction models, and their
combined checks. The catalogue loads the selected provider's metadata once, and
each generated check retains the model and combination used by its registered
implementation. Execution evidence and reports preserve those snapshots.

## Property definitions

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

`schema_version` identifies the property metadata format. The registered
definitions currently use format 2 and definition version 1. The model and
combined-check schemas leave this existing property format unchanged.

### Shape and binding

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

### Evidence and reports

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

## Transaction models

The [transaction-model schema](transaction-model.schema.json) describes an array
of records with four fields:

| Field | Meaning |
| --- | --- |
| `id` | Sequential model ID, such as `TxM-001` |
| `title` | Readable model name |
| `plutus_version` | Plutus ledger-language context format, such as `v3` |
| `description` | The contexts represented, including relevant fixed and variable features |

A changed model gets a new ID; an existing ID retains its meaning. Construction
facts belong in the description, while Lean code implements the construction.
The Plutus version identifies the context format; protocol and evaluator
configuration remain separate execution concerns.

The registered model IDs identify these context families:

| Model ID | Context family | Current property |
| --- | --- | --- |
| `TxM-001` | `EveryMint` | UP-001 |
| `TxM-002` | `EveryWithdraw` | UP-001 |
| `TxM-003` | `EveryPublish` | UP-001 |
| `TxM-004` | `EveryVote` | UP-001 |
| `TxM-005` | `EveryPropose` | UP-001 |
| `TxM-006` | `EverySpend` | UP-001 |
| `TxM-007` | Vesting Claim | UP-012 test profile |
| `TxM-008` | Vesting Cancel | UP-012 test profile |

The generic records live in
[`Candidates/transaction-models.json`](../Candidates/transaction-models.json).
The vesting records stay with the test profile in
[`Tests/UP012/transaction-models.json`](Tests/UP012/transaction-models.json).
UP-001 selects only purposes without a declared handler in the supplied validator.
UP-012 retains its existing guard for the original vesting artifact.

## Combined checks

The [combined-check schema](combined-check.schema.json) describes an array of
records linking a property definition to a model:

| Field | Meaning |
| --- | --- |
| `property` | Object containing the property `id` and `definition_version` |
| `tx_model` | Selected transaction-model ID |
| `limitations` | List of text entries explaining limitations of this combination |

The model describes construction facts. The combined check explains their
consequences for the selected property, such as which scenarios the check covers.
Descriptions stay in the referenced records, and execution produces the results.
One model can serve several properties, and one property can use several models
through separate combined checks.

The corresponding records live in
[`Candidates/combined-checks.json`](../Candidates/combined-checks.json) and
[`Tests/UP012/combined-checks.json`](Tests/UP012/combined-checks.json).
Registered generator code assigns each job its expected model ID. The catalogue
resolves the selected property/version/model combination, and generation attaches
the matching records. Descriptive metadata does not choose a different generator.

The schemas and [Lean readers](ModelMetadata.lean) check known fields and types.
Required/optional and list-cardinality policies remain open. Runnable bindings
must nevertheless resolve uniquely. The combined property's ID and definition
version must match the retained property record and job. Its `tx_model` must match
the registered model ID, and the model's Plutus version must match the target.
Missing, ambiguous, or mismatched selected bindings produce a preparation error.

### Applicability and evidence

An applicability obligation retains the same combination and model as the property
job that references it. Reporter checks this agreement using the existing exact
module/name reference, while preserving each job's role and observation. A passing
applicability check only qualifies its linked property's result.

Each job in `execution.json` and each check in `report.json` includes `txModelId`,
`transactionModel`, and `combinedCheck`. The latter two fields retain the complete
supplied records. The text report shows the model description and combination
limitations alongside the check. Changed or inconsistent snapshots prevent the
affected evidence from supporting a conclusive result. A preparation failure or
empty plan does not claim that any model check executed.

Direct API providers can remain explicitly metadata-free. Their records contain
no invented official bindings. The UP-012 retain-signer negative control clears
the official combined-check binding when it changes the property proposition.

The UP-012 models describe baseline contexts with one signer. The property removes
that signer to construct a second context; the result need not belong to the
baseline model family. Its `validScriptContext` conditions are property premises,
not guarantees of the constructor or proof of full ledger reachability.

### Example

These sample arrays describe the existing `EveryMint` context builder in
[`Formal/Universal/Properties.lean`](../Formal/Universal/Properties.lean) paired
with UP-001 for a target without a minting handler. The maintained records linked
above contain the current descriptions; executable registration remains in Lean.

Transaction-model metadata:

```json
[
  {
    "id": "TxM-001",
    "title": "Open minting context",
    "plutus_version": "v3",
    "description": "Minting contexts with arbitrary transaction information, policy ID, and redeemer. The constructor adds no ledger-validity conditions."
  }
]
```

Combined-check metadata:

```json
[
  {
    "property": {
      "id": "UP-001",
      "definition_version": 1
    },
    "tx_model": "TxM-001",
    "limitations": [
      "Covers minting invocations; other script purposes require separate checks.",
      "A counterexample may not correspond to a ledger-valid transaction."
    ]
  }
]
```

## Workflow-first rollout

Runtime metadata adoption covers the two registered workflow definitions. UP-012 remains
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
