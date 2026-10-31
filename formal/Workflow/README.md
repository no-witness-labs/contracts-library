# Plutus UPV workflow

Plutus UPV (Universal Property Verifier) checks universal properties against
compiled Plutus validators using ordinary Lean code and configured proof tools.
The prototype supports the documented Aiken-style Plutus V3 blueprint profile,
one selected validator, UP-001, and an experimental pinned UP-012 vesting suite.

| Guide | Use |
| --- | --- |
| [User guide](Docs/USER-GUIDE.md) | Prepare the tools, run the CLI, find outputs, and run tests |
| [Developer guide](Docs/DEVELOPER-GUIDE.md) | Understand metadata, bindings, source files, and component integration |
| [Validation history](Docs/VALIDATION.md) | Inspect evidence from earlier checkpoints and its limits |
| [PR #47 reconciliation](Docs/RECONCILIATION.md) | Review retained behavior and outstanding delivery gaps |

## Components and ownership

```text
Input → Generator → Executor → Reporter
```

Input selects a validator and validates its embedded compiled program. Generator
constructs obligations through a supplied provider. Executor runs Lean under a
shared execution budget and retains observations. Reporter qualifies those
observations and produces PASS, FAIL, or INCONCLUSIVE results.

| Location | Responsibility |
| --- | --- |
| [Input/](Input/README.md) | Supported artifact intake, decoding, and target descriptions |
| [Generator/](Generator/README.md) | Pure generation of Lean modules and declared check jobs |
| [Executor/](Executor/README.md) | Isolated runs, process deadlines, diagnostics, and evidence |
| [Reporter/](Reporter/README.md) | Expected/observed comparison, applicability, and summaries |
| `App/` | CLI entry points, candidate resolution, and application coordination |
| `Types/` | Shared target/input and generation/job contracts |
| `Metadata/` | Property/model metadata readers and binding validation |
| [Tests/](Tests/README.md) | Component controls and the UP001/UP012 workflow scenarios |
| [Formal/Properties](../Formal/Properties/README.md) | Native primary definitions, metadata, and category/code indexes |
| [Formal/TxModels](../Formal/TxModels/README.md) | Native context constructors and their metadata |
| `Candidates/` | Registered generation and composition adapters |

The four component entry modules and `Workflow.lean` remain public imports.
The components receive explicit inputs and do not import candidate or scenario
implementations. Application composition supplies those dependencies.

## Supported behavior and limits

- The runtime uses ordinary code, without AI services or Nix.
- Input accepts a blueprint with embedded compiled code and explicit Plutus
  version. It decodes the program before generation. Standalone CBOR and function
  targets need their own input contracts.
- Input preserves parameter descriptions; current adapters accept absent/empty
  parameters and reject unapplied nonempty lists.
- UP-001 checks nonacceptance for undeclared purposes within 5,000,000 CEK steps.
  Exhaustion satisfies this claim; explicit rejection is a different statement.
- UP-012 applies the experimental signer-removal definition to the fixed Claim
  and Cancel models. Its applicability obligations qualify the corresponding
  property obligations. It is not a general required-signer audit for new validators.
- A qualified, trustworthy FAIL takes aggregate precedence. Missing, interrupted,
  or untrusted evidence cannot establish PASS. An empty plan is INCONCLUSIVE.
- Solver observations inherit Blaster's SMT trust boundary. Model validity,
  ledger reachability, source correspondence, and protocol relevance are separate
  questions. Clients assess which reported claims matter to their protocol.
- Generated sources, inputs, reports, and raw logs appear only in ignored local
  output directories. Fixed fixtures remain committed for repeatable tests.

## Core boundary and next work

The agreed next core interface separates validator preparation from verification
of one property-definition/model combination, with its linked proof obligations.
That interface is not yet implemented: current providers and the CLI still bundle
several model combinations for a selected property. Later run orchestration can
repeat core attempts over validators and properties.

The current command defaults to UP-001. Batch selection, all/list/config syntax,
outer budget policy, expanded reports, additional input formats, typed parameter
application, and property-design improvements require separate reviewed work.
Issue #39 tracks the workflow; #33 tracks UP-012's semantic design and #66 tracks
the wider catalogue/cross-branch migration.

## Glossary

| Term | Meaning |
| --- | --- |
| Check target | The subject selected for checking; currently a validator |
| Target description | The compiled artifact and interface metadata passed from Input to Generator |
| Parameter description | Ordered interface metadata for configuration arguments, without applied values |
| Input artifact | The document or serialized program supplying a target; distinct from the target kind |
| Blueprint | A CIP-57 document describing validators and interfaces, with optional compiled content |
| Script CBOR | Serialized compiled Plutus code in a supported input representation |
| Property | A statement about target behavior |
| Candidate property | A proposed property whose definition or intended use remains under review |
| Transaction model | A family of contexts and constructed relationships; one model can serve several properties |
| Combined check / check variant | One property-definition version paired with a model and stated assumptions/limitations |
| Check definition | The property statement, model assumptions, applicability conditions, and expected observations specifying a check |
| Check job | A generated obligation with its expectation, scope, role, and execution identity |
| Applicability obligation | Establishes that the premises needed by a linked property check have a witness in the model |
| Candidate catalogue | References to maintained check implementations and supporting models |
| Run selection | The checks chosen by application defaults or supported explicit controls |
| Workflow test scenario | Candidate/model references, prepared target inputs, and expected outcomes for testing the assembled workflow |
| Check provider | Ordinary Lean generation code implementing the Generator contract |
| Generation plan | Modules, jobs, metadata, and notes for one generation request; currently it can bundle combinations |
| Job observation | An attributed solver result and diagnostics, before comparison with the declared expectation |
| Execution evidence | Retained sources, logs, process details, and observations for an attempt |
| Check report | Qualified expected/observed comparisons, preserving scope and incomplete outcomes |
