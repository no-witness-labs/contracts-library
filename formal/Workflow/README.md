# Workflow design

This document records the design for issue #39 and draft PR #52. Input,
Generator, and Executor now have Lean implementations and isolated tests, with
a bounded UP-001 execution example. Reporter still needs integration. The
[current usage guide](../docs/WORKFLOW.md) describes the Python workflow.

## Agreed decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Components | Input, Generator, Executor, and Reporter, each in its own folder | Give each responsibility a clear boundary |
| Location | Keep all four under `formal/Workflow/`, with shared interfaces and a thin entry point at the root | Keep the workflow together in one Lean project |
| Testing | Give each component its own tests and fixtures; test the assembled workflow separately | Verify components without requiring the full pipeline |
| Independence | Coordinate components through explicit interfaces, without hardcoded property IDs, validator names, or blueprint fields in the entry point | Support different checks and inputs through the same workflow |
| Runtime | Implement the workflow as ordinary code and configured proof-tool processes, without AI agents or model calls | Keep component behavior and tests independent of AI services |
| Initial target | Start with validators; defer function targets to a later contract extension | Establish a useful first scope without settling every future target kind |
| Initial input | Accept a blueprint containing the selected validator's compiled code; defer standalone CBOR plus metadata | Obtain the compiled artifact and its interface description from one input |
| Plutus version | Support Plutus V3 first; defer other versions | Match the existing runner and execution context |
| Parameters | Input preserves parameter descriptions and their order without applying values; Generator determines how a selected check uses them | Separate reading a validator description from constructing a check |
| Selection | Return one selected validator per Input request; orchestration can repeat requests for several validators | Keep the component contract small and make each result unambiguous |
| Missing metadata | Return a clear error for missing required metadata, including an explicit Plutus version; preserve missing optional metadata without guessed values | Avoid interpreting incomplete input under unsupported assumptions |
| Compiled-code decoding | Input uses the existing Lean decoder to check that embedded compiled code decodes into a Plutus program | Reject decoder errors before check generation without building another parser |
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

## What stays shared

| Component | Shared behavior | What varies between requests |
| --- | --- | --- |
| Input | Read the supported blueprint profile independently of property selection | The selected validator's compiled artifact and interface metadata |
| Generator | Construct jobs through the common generation contract | Property definitions, model configuration, and the validator information they use |
| Executor | Invoke the supported proof tools and retain observations | Generated jobs, execution limits, and observed outcomes |
| Reporter | Interpret observations using declared expectations and reviewed exceptions | Check-specific expectations, results, and applicable review configuration |

For the same artifact and selected validator, Input returns the same description
whether the caller later requests UP-001 or another property. Generator produces
different jobs from that description. Executor and Reporter use the common job
and observation contracts, without hardcoded property IDs.

Additional input formats or proof backends may require their own adapters.
Those differences belong to format and tool support, rather than to the choice
of property.

## Targets and input formats

Keep the kind of target separate from the format used to supply it. A validator
is the initial target kind. A blueprint or a separate script file is an input
representation. See the [workflow glossary](CONTEXT.md).

The shared `TargetDescription` in `Types.lean` contains the target identity,
encoded compiled code, handler and parameter descriptions, and optional
definitions and compiler metadata. Schema descriptions use the preserved schema
JSON vocabulary of the first adapter. Source text and path remain separate in
`InputResult`. Generator integration should consume this description rather
than read the original blueprint document. The first UP-001 provider now uses
that handoff. `Jobs.lean` defines generated modules, check jobs, expected solver
results, and the generation-plan status for downstream components.

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
| Generator extensions | Port typed parameter handling and additional checks while preserving each candidate's statements and explicit limits |
| Reporter integration | Compare declared expectations with observed results, preserving incomplete-run and review-exception rules |
| Function support | Extend the target contract after agreeing a concrete function use case and its checks |

The [Input component](Input/README.md) documents the implemented input profile,
error contract, fixture harness, and remaining limits. The
[Generator component](Generator/README.md) documents plan generation, the first
provider, and the distinction between type-checking and proof execution. The
[Executor component](Executor/README.md) documents process budgets, raw
observations, retained evidence, and the inconclusive vesting execution.

## Next work

Review the Executor checkpoint, then connect Reporter to its observations and
the jobs' declared expectations. Further component implementation requires a
scoped proposal and confirmation.
