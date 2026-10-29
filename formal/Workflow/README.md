# Workflow design

This document records the design for issue #39 and draft PR #52. All four
components now have Lean implementations and isolated tests. A thin command
connects them for the first unparameterized UP-001 example:

```sh
cd formal
lake exe universal /path/to/plutus.json module.validator --check UP-001 --timeout-ms 120000
```

The [CLI quickstart](QUICKSTART.md) covers setup and examples of all three outcomes.
The [check file map](CHECK-FILES.md) locates `EveryMint`, `EveryWithdraw`, and the
other definitions used by generated checks. The experimental UP-012 provider
also runs the existing vesting signer-removal suite through the same components;
see the [quickstart](QUICKSTART.md) for its command and scope.
Use a prepared checkout with the pinned dependencies and tools. The
[Reporter guide](Reporter/README.md) describes output and exit codes; the
[workflow usage guide](../docs/WORKFLOW.md) summarizes the supported CLI.

## Agreed decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Components | Input, Generator, Executor, and Reporter, each in its own folder | Give each responsibility a clear boundary |
| Location | Keep all four under `formal/Workflow/`, with shared interfaces and a thin entry point at the root | Keep the workflow together in one Lean project |
| Testing | Collect test assets under `Workflow/Tests/`, with UP001 and UP012 workflow scenarios and separate component unit checks | Keep the reusable engine separate from example targets and expected results |
| Independence | Coordinate components through explicit interfaces, without hardcoded property IDs, validator names, or blueprint fields in the entry point | Support different checks and inputs through the same workflow |
| Runtime | Implement the workflow as ordinary code and configured proof-tool processes, without AI agents or model calls | Keep component behavior and tests independent of AI services |
| Reporting | Start with a plain summary and JSON output; defer branding and expanded content | Focus on correct, inspectable outcomes |
| Initial target | Start with validators; defer function targets to a later contract extension | Establish a useful first scope without settling every future target kind |
| Initial input | Accept a blueprint containing the selected validator's compiled code; defer standalone CBOR plus metadata | Obtain the compiled artifact and its interface description from one input |
| Plutus version | Support Plutus V3 first; defer other versions | Match the existing runner and execution context |
| Parameters | Input preserves parameter descriptions and their order without applying values; Generator determines how a selected check uses them | Separate reading a validator description from constructing a check |
| Selection | Return one selected validator per Input request; orchestration can repeat requests for several validators | Keep the component contract small and make each result unambiguous |
| Missing metadata | Return a clear error for missing required metadata, including an explicit Plutus version; preserve missing optional metadata without guessed values | Avoid interpreting incomplete input under unsupported assumptions |
| Compiled-code decoding | Input uses the existing Lean decoder to check that embedded compiled code decodes into a Plutus program | Reject decoder errors before check generation without building another parser |
| Language | Prefer Lean throughout; use experiments to justify any temporary Python implementation | Reuse working code while establishing the cost of integration |
| Integration example | Use UP-001 for the first bounded integration example | Exercise the interfaces with an existing check |
| UP-001 bound | Use 5,000,000 CEK steps with the existing raw redeemer and open context domains | Match PR #47's default bound after semantic review and individual proof experiments |
| Delivery | Keep issue #39, branch `feat/39-developer-workflow`, and draft PR #52 as the workflow task | Consolidate the relevant work from PR #47 in one delivery |
| Applicability | Generator explicitly identifies applicability obligations and links them to the property obligations they qualify | Let downstream components distinguish an unusable scenario from a property counterexample |
| Candidate catalogue | Reference maintained candidate implementations and supporting models through a catalogue | Add candidates without embedding their identities or example validators in the core components |

The workflow and test folders are:

```text
formal/Workflow/
├── Input/
├── Generator/
├── Executor/
├── Reporter/
└── Tests/
    ├── UP001/
    ├── UP012/
    └── Unit/
```

The reusable components and orchestration do not import candidate or test
implementations. `Candidates/` contains candidate code, and the UP-012 test
profile owns its pinned artifact and transaction model. Explicit applicability
relationships remain an approved design change for a separate checkpoint.

Input reads supported artifacts and produces a target description. Generator
produces check jobs from that description and selected property definitions.
Executor runs the jobs and retains observations. Reporter compares observations
with declared expectations and produces a report and exit code. Reviewed
exception handling remains a later extension.

## What stays shared

| Component | Shared behavior | What varies between requests |
| --- | --- | --- |
| Input | Read the supported blueprint profile independently of property selection | The selected validator's compiled artifact and interface metadata |
| Generator | Construct jobs through the common generation contract | Property definitions, model configuration, and the validator information they use |
| Executor | Invoke the supported proof tools and retain observations | Generated jobs, execution limits, and observed outcomes |
| Reporter | Compare observations with declared expectations | Check-specific expectations and results; reviewed exceptions remain future work |

For the same artifact and selected validator, Input returns the same description
whether the caller later requests UP-001 or another property. Generator produces
different jobs from that description. Executor and Reporter use the common job
and observation contracts, without hardcoded property IDs.

Additional input formats or proof backends may require their own adapters.
Those differences belong to format and tool support, rather than to the choice
of property.

## Candidate composition and report direction

[`Candidates/Catalogue.lean`](../Candidates/Catalogue.lean) is the current thin
composition index. It references `Candidates.UP001` and the experimental
`Workflow.Tests.UP012.Profile`, which binds the original candidate propositions
to its vesting scenario. `Workflow/CLI.lean` supplies that resolver to the generic
`Workflow.Main.run` entry point. Candidate code stays outside the engine.
Workflow tests reference that code and supply example targets, scenario-specific
models or harnesses, and expected outcomes. Fixed fixtures support these tests;
normal runs supply their own required inputs.

The reusable engine receives its candidate resolver and selected target through
its interfaces. It does not own the candidate list or a particular validator's
test setup. Adding a candidate should require providing its implementation and
catalogue reference rather than editing the engine.

The agreed product direction is to run maintained property checks and report
each attempted check with its description, assumptions, limitations, and result.
Clients review which results matter to their protocol afterward. Choosing
properties in advance is optional; enable/disable controls remain a later feature.

The project maintains reusable property definitions and transaction models.
Each check uses the supplied validator as an input; supporting a new validator
must not require a bespoke transaction model for it. Known validators supply
workflow test fixtures. The current UP-012 vesting profile is an experimental
integration example, not the required setup process for client validators.

A property may have several definition versions and run against several models.
Models may also support several properties. Each reported check must identify
the definition version and model it used, preserving their scope and limitations.
Solver validity concerns the formal statement; whether that statement is a
requirement of the client's protocol is a separate assessment.

These are design requirements, not additional implemented CLI capabilities.
The current command still resolves one provider and defaults to UP-001. Catalogue
format, version/model identifiers, default run contents, configuration, and
enable/disable syntax remain open. An all-candidates mode, explicit lists, and
client configuration remain possible controls.

UP-012's signer-removal definition remains a workflow integration test.
Improving its meaning, generic coverage, and security value belongs in a separate
property PR, outside issue #39 and this workflow PR. Its passing test results
establish only the current bounded example.

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
| Reporting extensions | Add reviewed exceptions, branding, and expanded content without weakening incomplete-run handling |
| Function support | Extend the target contract after agreeing a concrete function use case and its checks |

The [Input component](Input/README.md) documents the implemented input profile,
error contract, fixture harness, and remaining limits. The
[Generator component](Generator/README.md) documents plan generation, the first
provider, and the distinction between type-checking and proof execution. The
[Executor component](Executor/README.md) documents process budgets, raw
observations, and retained evidence. The
[Reporter component](Reporter/README.md) documents the simple report, exit codes,
and full prototype command.

## Next work

The prototype already connects all four Lean components and retains local
sources, logs, and reports. The UP001 and UP012 workflow scenarios cover passing,
failing, unsupported, malformed-input, and timeout cases. The next checkpoints
below are a proposed work order; code changes require a bounded implementation
proposal and confirmation.

- [ ] **Choose the product name and add one verbose test command.** The name must
  communicate formal verification of universal properties and connect to
  Plutus/Cardano. Choose the name and launcher before implementation. The intended
  interface is `<name> test` alongside `<name> run ...`. Cover all four
  component unit suites, all three integration suites, and UP001/UP012. Run each
  suite once, sequentially, including its existing candidate checks. Show suite
  and case names, commands, progress, stdout/stderr, elapsed time, expected
  negative outcomes, and a final summary. Make verbose logging the default and
  retain detailed logs under ignored local output. Print start messages before
  buffered solver calls. Build explicit workflow targets; do not run stale
  executables after a build failure. Continue independent suites after a test
  failure. Return success only when every required suite ran and passed. This is light engineering;
  keep real solver runs sequential and omit redundant optional integration probes.
- [ ] **Finish the result-policy decisions.** Review false, unknown, missing,
  and interrupted applicability; trustworthy completed results beside unrelated
  failures; and overall status/exit codes for mixed FAIL/INCONCLUSIVE runs. Use
  a small outcome table and Astra review. Preserve the approved rules: disproved
  applicability makes its linked property INCONCLUSIVE, and independent completed
  results remain visible. Do not treat partial output from a killed compiler as
  a completed proof.
- [ ] **Implement the agreed applicability and partial-result rules.** Link each
  supporting obligation to the exact property obligation it qualifies. Preserve
  raw observations and reasons, and distinguish local failures from failures that
  undermine the evidence for other results. Verify the policy with controlled
  cases, including separate Claim/Cancel links and mixed outcomes. This is an
  engineering checkpoint after policy approval; it needs no new property proofs.
- [ ] **Agree and carry the minimum check metadata.** Use
  [issue #65](https://github.com/no-witness-labs/contracts-library/issues/65) for
  the field decisions, including independent definition/model versions and clear
  descriptions and limitations. Then carry the agreed identity and target binding
  unchanged through Generator, Executor, and Reporter. Demonstrate one definition
  with different models and model versions without confusing their observations.
  Metadata discussion can proceed alongside the test-command work; implementation
  follows the reviewed contract.
- [ ] **Complete the evidence for failed attempts.** Retain readable input even
  when parsing or decoding fails, plus the invocation, options, and failure phase.
  Record the actual executed commands and their context. Unreadable inputs need
  an explicit reason instead of an invented snapshot. Verify malformed input,
  preparation failures, and timed-out runs with small controlled cases. This is
  light engineering; full dependency hashing can remain a follow-up.
- [ ] **Run multiple maintained check variants for one validator.** Decide the
  initial run contents and time-budget policy. Reuse separate generation/execution
  plans so one unsupported or failed variant does not erase other attempts.
  Retain a distinct result and evidence reference for every attempted variant,
  including variants that could not run. Validate the boundary with two variants
  sharing declaration names and with mixed successful, failing, and incomplete
  attempts. Start with sequential orchestration rather than a scheduler framework.
- [ ] **Complete the regression and delivery review.** Run focused tests during
  each checkpoint and finish with the aggregate test command. Verify the
  documented CLI from a prepared checkout. Keep reports and evidence attributable
  to the exact run. Reconcile remaining [PR #47 exclusions](RECONCILIATION.md), update
  the supported-scope documentation, and prepare the draft PR for owner review.

Property-definition improvements, including UP-012 signer removal, remain in
separate property work. Enable/disable syntax, richer report branding, additional
input formats, typed parameter application, hosted CI, and broader packaging
remain follow-ups. The test-command naming and minimal launcher decision above
do not require a general installation framework.

The [validation history](VALIDATION.md) preserves the existing model and CEK
bounds and the Blaster trust boundary. Input needs no redesign for these
checkpoints; extend it only when an agreed input contract requires it.
