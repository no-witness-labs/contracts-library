# Generator component

Generator receives a supplied check provider, a `TargetDescription`, and an
isolated module prefix. It returns a `GenerationPlan` containing Lean sources
and check jobs. It performs no file reads/writes, compiler invocations, or solver
calls.

## Contract

Import `Workflow.Generator` and call:

```lean
Workflow.Generator.generate provider target modulePrefix
```

Generator receives two logical inputs: the validator description from Input,
and a configured check provider. The provider binds the property definition to any
model or harness it needs, together with its expectations and scope. The module
prefix is internal naming information.

UP-001 binds its definition to generic per-purpose contexts. UP-012's test
profile binds its four propositions to the typed vesting data and Claim/Cancel
transaction shapes. Blueprint metadata alone does not supply those transaction
shapes; the current profile supplies them explicitly.

A provider supplies property-specific generation through the common interface.
The reusable Generator has no built-in candidate catalogue, validator snapshot,
or transaction model. The application supplies those dependencies.

Each job declares its property ID, name, module, proposition, expected solver
result, and scope. A plan carries the target identity, generated modules, jobs,
and scope notes. A plan without jobs has status `noObligations`; it provides no
passing verdict. Module prefixes must use safe Lean module-name segments.

Provider definitions own their applicability restrictions, model assumptions,
and expected results. The approved design will add explicit applicability
relationships in a later checkpoint; the structural refactor preserves the
current job contract and outcome behavior.

## Candidate composition

The current CLI uses [Candidates/Catalogue.lean](../../Candidates/Catalogue.lean)
through [CLI.lean](../CLI.lean). The generic orchestration entry point receives
the resolver as an argument. Additional catalogue formats and selection modes
remain design work.

UP-001 generation lives in [Candidates/UP001.lean](../../Candidates/UP001.lean).
The original UP-012 propositions live in
[Candidates/UP012.lean](../../Candidates/UP012.lean), while their experimental
vesting model and artifact guard belong to the
[UP-012 scenario](../Tests/UP012/README.md). Candidate definitions have one source;
scenario tests reference them.

## Tests

From `formal/`:

```sh
lake exe workflow_generator_tests
lake exe workflow_generator_integration
```

The first command runs only generic contract checks with stub providers. The
UP001 and UP012 workflow suites own their candidate-specific declaration/profile
checks. The second command preserves the Input-to-Generator type-checking check;
it compiles support and proposition definitions without proving them.

The [test index](../Tests/README.md) lists the two complete workflow scenarios
and component checks. The [validation history](../VALIDATION.md) keeps generation,
type-checking, and actual solver observations distinct.
