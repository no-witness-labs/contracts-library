# Generator component

Generator consumes a `TargetDescription` and returns a `GenerationPlan` in Lean.
It does not read a blueprint, write files, invoke a compiler, or run a solver.
The coordinator supplies an ordinary Lean check provider and an isolated module
prefix.

## API

Import `Workflow.Generator` and call
`Workflow.Generator.generate provider target modulePrefix`.

The first provider is `Workflow.Generator.OtherPurpose.provider`. It generates
the UP-001 candidate. The common entry point accepts other provider functions;
property-specific definitions stay outside the generic generation code.
The thin command selects registered providers through `Catalogue.lean`.

`GenerationPlan` contains generated module names and source, check jobs, target
identity, and scope notes. Each job declares its property ID, theorem name,
module, proposition, and expected solver result. Executor and Reporter can use
this metadata without knowing what a property ID means.

A plan with no jobs has status `noObligations`. The status does not mean a check
passed. The caller owns file placement and must use an isolated namespace;
Generator itself has no file-writing effects.

## First provider: UP-001

The unparameterized statements derive from
[candidate PR #49](https://github.com/no-witness-labs/contracts-library/pull/49)
at `b44b6b0757a75d79b79a4de4712523ee3978760e`. The provider keeps its context
helpers and negated-acceptance formula:

- Quantify over raw redeemer data and the existing full per-purpose context.
- Check each purpose missing from the supplied handler declarations.
- Use the reviewed bound of 5,000,000 CEK steps for this provider.
- Treat fuel exhaustion as satisfying no acceptance within that bound, rather
  than establishing an explicit script error.

The candidate used `ledgerFuel`, which remains 1,000,000 for other candidates.
This provider now emits literal `5000000`, matching PR #47's default bound while
keeping the broader domains. The owner approved this semantic change after
review and successful isolated experiments for each of vesting's five
undeclared purposes. See the [reconciliation](../RECONCILIATION.md) and
[validation history](../VALIDATION.md).

The generated support module embeds the original encoded code and defines the
same context-only argument list and bounded acceptance predicate. Datum and
redeemer schema translation are unnecessary for this unparameterized property.

Nonempty parameter lists return an explicit unsupported error in this first
checkpoint. The Python candidate has typed parameter translation; porting it
requires preserving its parameter domains and quantifiers. Input continues to
accept and preserve parameter descriptions. Absent and explicit empty parameter
lists both permit this provider's context-only generation.

The provider accepts Plutus V3 targets only. Module-prefix segments must start
with an uppercase ASCII letter. All six declared purposes produce no obligations; an exported
fallback does not count as a declared purpose.

## Tests

From `formal/`, with the pinned dependencies prepared:

```sh
lake build Workflow workflow_generator_tests workflow_generator_integration
lake exe workflow_generator_tests
lake exe workflow_generator_integration
```

The unit harness constructs target descriptions directly. It checks the golden
reviewed declarations, job metadata, module-prefix handling, empty plans,
unsupported parameterized targets, and an independent sample provider with a
different expected result.

The integration harness reads Input's fixture, calls Generator, and compiles
the generated support module and proposition definitions in a temporary
directory. It checks source preservation and removes only that directory.
The proposition definitions type-check the generated statements without
discharging them. No Blaster proof runs in this harness.

To include the repository's vesting blueprint:

```sh
lake exe workflow_generator_integration ../onchain/plutus.json linear_vesting.linear_vesting
```

Both fixture and vesting type-checking runs passed. These results establish
generation and type-checking, not proof validity. The actual generated `Checks`
module retains `by blaster` and inherits the candidate's proof trust boundary.
The shared command now connects [Executor](../Executor/README.md) and
[Reporter](../Reporter/README.md). The [validation history](../VALIDATION.md)
separates the original 1,000,000-step run from the reviewed 5,000,000-step
checkpoint. Generation/type-checking and solver results remain separate forms
of evidence.
