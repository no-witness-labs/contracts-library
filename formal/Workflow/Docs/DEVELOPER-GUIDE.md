# Develop the Plutus UPV workflow

The [overview](../README.md) defines component ownership and terminology; the
[user guide](USER-GUIDE.md) covers CLI operation. This guide connects maintained
definitions and models to generated obligations, metadata, and evidence.

## Definitions, models, and adapters

The [property bank](../../Formal/Properties/README.md) organizes native definitions
and required metadata by category/code. Root/category indexes use checked Lean
names and metadata paths. Each candidate has one primary definition; its file can
also contain applicability predicates, helpers, and lemmas.

The [transaction-model bank](../../Formal/TxModels/README.md) owns native context
constructors and their metadata in individual `Definitions/TxMNNN.lean` modules.
Its index exports metadata as JSON for the reader. Shared model helpers and vesting
types stay at the bank root; the bank imports no workflow modules.

[Candidates/Catalogue.lean](../../Candidates/Catalogue.lean) composes fixed executable
adapters. UP-001 uses [Candidates/UP001.lean](../../Candidates/UP001.lean); UP-012
uses [Candidates/UP012.lean](../../Candidates/UP012.lean) with the
[pinned test profile](../Tests/UP012/Profile.lean). Metadata does not choose code.
[App/ProductCLI.lean](../App/ProductCLI.lean) supplies the resolver to the generic
`Workflow.Main.run` declaration in [App/Main.lean](../App/Main.lean).
[App/CLI.lean](../App/CLI.lean) retains the legacy `universal` executable.

Current providers can emit several combinations in a plan. The agreed future
core separates preparation from verification of one combination; this cleanup
does not add that API or batch selection. Preserve each definition's actual model
domain, bounds, and restrictions when adapting it.

## Metadata and schemas

| Record | Authoritative source | Schema/reader |
| --- | --- | --- |
| Property | Each property's `metadata.json` in Formal/Properties | [Record schema](../../Formal/Properties/property-definition.schema.json), [Metadata/Property.lean](../Metadata/Property.lean) |
| Transaction model | Metadata beside its native constructor, exported through the model index | [Model schema](../../Formal/TxModels/transaction-model.schema.json), [Metadata/TxModel.lean](../Metadata/TxModel.lean) |
| Combined check | [Generic bindings](../../Candidates/combined-checks.json) or [experimental vesting bindings](../Tests/UP012/combined-checks.json) | [Combined-check schema](../Metadata/combined-check.schema.json), [Metadata/TxModel.lean](../Metadata/TxModel.lean) |

The property record groups identity (`id`, `definition_version`, `title`,
`category`), explanation (`summary`, `claim`, `purpose`), scope
(`relevance_conditions`, `preconditions`, `limitations`), formalization
(`primary`, `theorems`), and `references` using label/target pairs.
`schema_version` identifies its metadata format, currently 2; maintained property
definitions use version 1. `primary` identifies the native mathematical statement,
not the source-generation adapter. Static theorem names are not results for the
supplied target; current records have no static target proofs.

Models have exactly four known descriptive fields: `id`, `title`, `plutus_version`,
and `description`. A changed model gets a new TxM ID, keeping existing meanings
stable. Construction facts belong in the description. The Plutus version describes
the context format; execution semantics also depend on the configured proof tools.

A combined check contains `property: {id, definition_version}`, `tx_model`, and
`limitations`. It explains how the model constrains that property's coverage or
interpretation. One model may serve several properties, and one property may use
several models through distinct combinations.

Schemas and readers check known fields and types, preserving omitted fields,
explicit empty strings, and empty lists. They reject wrong types, nulls, and
unknown keys. Individual-field optionality and list-cardinality policy remain
open. Structural validity does not make a record runnable or establish a theorem.

Runtime association resolves the selected property ID/version uniquely against
fixed code. A supplied primary must match the index. The combined check must match
the property and registered model ID, and the model's Plutus version must match
the target. Missing, ambiguous, or inconsistent selected bindings fail preparation.
References are informational: the workflow does not fetch, import, or execute them.

The old `Workflow/property-definition.schema.json` collection wrapper is removed.
Validate individual records against the property-bank schema; consumers of arrays
can wrap that record schema with `type: "array"` and `items` referencing its `$id`.
`PropertyDefinition.read`/`parseList` still support collections; `readRecord` reads
one property object. Module path migrations are listed below. The separate legacy
schemas under repository `docs/property-catalogue/` remain unchanged; issue #66
tracks their wider migration and other branches.

## Generated goals and supporting files

| Property/model application | Native definition/model |
| --- | --- |
| UP-001 mint | [UP001 statement](../../Formal/Properties/Universal/UP001/Definition.lean), [TxM-001 / EveryMint](../../Formal/TxModels/Definitions/TxM001.lean) |
| UP-001 withdraw | [TxM-002 / EveryWithdraw](../../Formal/TxModels/Definitions/TxM002.lean) |
| UP-001 publish/certify | [TxM-003 / EveryPublish](../../Formal/TxModels/Definitions/TxM003.lean) |
| UP-001 vote | [TxM-004 / EveryVote](../../Formal/TxModels/Definitions/TxM004.lean) |
| UP-001 propose | [TxM-005 / EveryPropose](../../Formal/TxModels/Definitions/TxM005.lean) |
| UP-001 spend, when undeclared | [TxM-006 / EverySpend](../../Formal/TxModels/Definitions/TxM006.lean) |
| UP-012 Claim | [Shared UP012 definition](../../Formal/Properties/Universal/UP012/Definition.lean), [TxM-007](../../Formal/TxModels/Definitions/TxM007.lean) |
| UP-012 Cancel | [TxM-008](../../Formal/TxModels/Definitions/TxM008.lean) |

Every* models expose full `TxInfo` and purpose fields; the theorem supplies a raw
redeemer. [Common.mkCtx](../../Formal/TxModels/Common.lean) assembles the context.
UP-001 selects only purposes absent from the target's declared handlers, applying
acceptance within 5,000,000 steps. It adds no ledger-validity premise.

UP-012 applies one primary statement and a supporting applicability predicate to
Claim and Cancel, producing four obligations. Baseline models have one signer;
the property removes it to construct a second context outside that baseline family.
Its `validScriptContext` conditions are explicit premises, not guarantees of the
constructor or evidence of ledger reachability. The profile accepts only the
original unparameterized vesting artifact.

Adapters unfold shared definitions before Blaster, preserving goal polarity and
the expanded formulas. Tests keep kernel-checked equivalences to frozen legacy
formulas. The retain-signer negative control uses independent legacy formulas and
clears official metadata when changing the property proposition.

| Generated file | Contents |
| --- | --- |
| `Generated/Workflow/Types.lean` | Embedded compiled program, argument conversion, acceptance predicate; UP-012 also aliases native data/redeemer types and defines rejection |
| `Generated/Workflow/Tx.lean` (UP-012) | Aliases for native Claim/Cancel model types, constructors, and datum helper |
| `Generated/Workflow/Checks.lean` | Concrete target/model theorem expressions and tactic calls |

[Formal/Universal/Properties.lean](../../Formal/Universal/Properties.lean) retains
current context aliases and evaluation/signatory helpers. UP-012 uses its
`rejectedWithin` predicate and 1,000,000-step `ledgerFuel`; UP-001 supplies literal
5,000,000 to its acceptance predicate. These are distinct rejection meanings.

Pinned dependencies are identified by [lake-manifest.json](../../lake-manifest.json).
Local sources under `.lake/packages/` include `CardanoLedgerApi/V3/Contexts.lean`,
`CardanoLedgerApi/IsData/Class.lean`, `PlutusCore/UPLC/CekMachine.lean`, and
`Blaster/Command/Tactic.lean`. Dependency versions and historical measured runs
remain in [validation history](VALIDATION.md); they do not establish source/ledger
correspondence beyond the checked model.

## Attribution, applicability, and failure evidence

The catalogue loads metadata once. The generation plan, execution observations,
and report preserve exact snapshots. `propertyDefinition` retains the property
record. Each job/row retains `txModelId`, `transactionModel`, `combinedCheck`, and
the submitted `statement`, identified by module/name. Snapshot changes prevent
the affected evidence from supporting a conclusive result; raw observations remain.
The theorem expression depends on the imported native definition, so it is not
a complete source/dependency fingerprint.

An applicability obligation has the same model/combination as its explicitly
linked property job. Reporter checks the exact module/name link, role, expected
Valid result, and snapshot agreement. Successful applicability qualifies only the
property's own observation. Falsified or unavailable applicability leaves the
linked property INCONCLUSIVE. Independent trustworthy failures retain precedence;
untrusted or incomplete module evidence cannot establish a passing property.

Direct API providers can remain explicitly metadata-free. Known property metadata
survives intake, generation, and execution-preparation failure reports when lookup
succeeds. If intake and catalogue lookup both fail, intake retains precedence.
Readable failed input and effective run arguments are retained by the coordinator.
See the user guide for `input.json`, `invocation.json`, and actual attempted
compiler command details in `execution.json`.

Generated output remains local. Tests that use fixed validators/models are evidence
of those bounded scenarios; their fixtures are not client onboarding requirements.
Generalizing UP-012 or redefining its required-signer meaning remains separate work.

## Module paths and validation

Existing workflow declaration names remain available. Reporter status/row types
are compatibility aliases to Assessor. Update module imports to these paths:

| Former import | Current import |
| --- | --- |
| `Workflow.Main` | `Workflow.App.Main` |
| `Workflow.ProductCLI` | `Workflow.App.ProductCLI` |
| `Workflow.CLI` | `Workflow.App.CLI` |
| `Workflow.Types` | `Workflow.Types.Target` |
| `Workflow.Jobs` | `Workflow.Types.Jobs` |
| `Workflow.PropertyDefinition` | `Workflow.Metadata.Property` |
| `Workflow.ModelMetadata` | `Workflow.Metadata.TxModel` |

The four component imports and `import Workflow` remain available. Executables
remain `plutus-upv` and `universal`; Lake roots now point into App/. Imports in
other branches must follow this table when integrating the cleanup.

Use component tests while changing their contracts, then run `./plutus-upv test`
from `formal/`. The [test index](../Tests/README.md) lists focused commands and
intentional negative controls. A fresh build must succeed before running test
executables. New properties/models need an implemented registered binding and
appropriate applicability/integrity tests; adding metadata alone cannot run a check.

## Callable single-check API

Import `Workflow.App.Verification` for separately callable preparation and one-check
verification. Preparation returns the source snapshot and an intake result. A
configured engine holds operational settings once; `verifyOne` takes the prepared
validator and configured check as its two logical inputs.

```lean
import Workflow.App.Verification
import Candidates.Catalogue

open Workflow

def verifyMint (leanPath : String) : IO Assessor.CheckResult := do
  let preparation ← Verification.prepare "Workflow/Tests/UP001/Inputs/plutus.json" "vault.vault"
  let prepared ← IO.ofExcept (preparation.result.mapError toString)
  let check ← IO.ofExcept (← Candidates.Catalogue.loadCheck "UP-001" 1 "TxM-001")
  let engine : Verification.Engine := {
    options := { leanPath, budgetMs := 120000, outputRoot := some "output" } }
  engine.verifyOne prepared check
```

The caller prepares the Lean dependency search path as it does for Executor.
Timeout, tool commands, and output location are engine configuration, distinct
from the CEK bound inside the registered property/model binding. Metadata belongs
to the configured combo and is retained with the result.

The catalogue resolves only the exact registered property/version/model. A new
JSON record cannot add executable code. Single-model adapters generate only the
chosen obligations: one undeclared purpose for UP-001, or one UP-012 main/applicability
pair. The core rejects mixed bindings, support-only plans, orphan applicability,
and empty plans containing executable modules. Registered generators remain trusted
code; metadata checks alone cannot inspect arbitrary Lean semantics. Tests check
the exact selected theorem set across generated sources.

Each call uses the captured validator source without rereading and returns the
[Assessor's six-field CheckResult](../Assessor/README.md). It prints nothing.
An attempt retains `input.json`, `check-result.json`, and execution files when
available in a fresh run directory. Unsupported or empty attempts keep the selected
combination and explanation; empty means INCONCLUSIVE. Preparation failure stays
an intake result because there is no prepared validator to verify.

The result references files found during retention and exposes the prepared-input
path only after a successful write. If creating/saving evidence fails, the returned
result is INCONCLUSIVE with reasons. One inherited limitation remains: if Executor
cannot write `execution.json`, it returns an error without its existing directory
reference. The core saves a separate incomplete attempt; earlier raw files may
remain local without links in that result. This API does not promise complete
recovery from every filesystem failure.

Current CLI options, bundled behavior, shared run budgets, and reports remain
available through the existing path. The callable API is the single-combination
boundary for later orchestration. Multi-validator/property loops and a final
branded report are not introduced by this checkpoint.
