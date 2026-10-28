# Workflow design

This document records the agreed design and open questions for issue #39 and
draft PR #52. The component implementations have not moved into this directory.
The [current usage guide](../docs/WORKFLOW.md) describes the existing prototype.

## Agreed decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Components | Input, Generator, Executor, and Reporter, each in its own folder | Give each responsibility a clear boundary |
| Location | Keep all four under `formal/Workflow/`, with shared interfaces and a thin entry point at the root | Keep the workflow together in one Lean project |
| Testing | Give each component its own tests and fixtures; test the assembled workflow separately | Verify components without requiring the full pipeline |
| Independence | Coordinate components through explicit interfaces, without hardcoded property IDs, validator names, or blueprint fields in the entry point | Support different checks and inputs through the same workflow |
| Initial target | Start with validators; defer function targets to a later contract extension | Establish a useful first scope without settling every future target kind |
| Initial input | Accept a blueprint containing the selected validator's compiled code; defer standalone CBOR plus metadata | Obtain the compiled artifact and its interface description from one input |
| Plutus version | Support Plutus V3 first; defer other versions | Match the existing runner and execution context |
| Language | Prefer Lean throughout; use experiments to justify any temporary Python implementation | Reuse working code while establishing the cost of integration |
| Integration example | Use UP-001 for the first bounded integration example | Exercise the interfaces with an existing check |
| Delivery | Keep issue #39, branch `feat/39-developer-workflow`, and draft PR #52 as the workflow task | Consolidate the relevant work from PR #47 in one delivery |

The planned component folders are:

```text
formal/Workflow/
├── Input/
├── Generator/
├── Executor/
└── Reporter/
```

Input reads supported artifacts and produces a target description. Generator
produces check jobs from that description and selected property definitions.
Executor runs the jobs and retains observations. Reporter combines observations,
declared expectations, and reviewed exceptions into a report and exit code.

## Targets and input formats

Keep the kind of target separate from the format used to supply it. A validator
is the initial target kind. A blueprint or a separate script file is an input
representation. See the [workflow glossary](CONTEXT.md).

The proposed shared description identifies the target, its compiled artifact,
and available interface metadata. Its exact fields and supported metadata still
need review. Generator should consume this description rather than blueprint
JSON fields.

Function targets remain a future extension. Their representation, arguments,
result contract, and applicable checks need a separate decision. Starting with
validators does not promise support for arbitrary functions in this delivery.

## Where CBOR fits

Concise Binary Object Representation (CBOR) is the serialization format involved
in the compiled-script input.

[CIP-57](https://cips.cardano.org/cip/CIP-57) describes a blueprint containing
validator interface schemas and optional compiled code. Its `compiledCode`
field contains the CBOR-encoded serialized Flat script. For this workflow, an
executable check needs the compiled artifact as well as its required metadata.

Separate CBOR input would need an explicit contract for its encoding, Plutus
version, and any interface metadata required by the selected checks. The
workflow must not invent datum types, parameter types, or declared handlers from
the presence of script bytes alone.

The first version therefore accepts a blueprint with embedded compiled code.
A metadata-only blueprint and a standalone CBOR file fall outside that initial
input contract. See the [Input contract](Input/README.md) for the agreed scope
and remaining questions.

Preserve the supplied artifact and record its identity. Keep format decoding,
metadata validation, source correspondence, and proof results distinct.

## Open decisions

| Question | Current proposal |
| --- | --- |
| Selection | Return one selected validator per Input request; allow orchestration to repeat requests later |
| Supported validator features | Specify parameter handling, blueprint compatibility, and required metadata before implementation |
| Shared target description | Agree the metadata representation, missing-information behavior, and error contract |
| Function support | Extend the target contract after agreeing a concrete function use case and its checks |

The implementation does not yet provide these proposed input guarantees.

## Next work

Review the Input contract and isolated fixtures first, then the remaining
component contracts. Map existing prototype behavior to the agreed boundaries
before extracting or translating code. Implementation requires separate
confirmation after reviewing the concrete change and its checks.
