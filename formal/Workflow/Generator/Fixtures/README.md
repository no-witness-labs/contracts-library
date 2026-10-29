# UP-001 declaration fixture

`up001-declarations.txt` contains the reviewed unparameterized UP-001 theorem
declarations for a validator declaring `spend`. They derive from candidate PR #49 at
`b44b6b0757a75d79b79a4de4712523ee3978760e`.

The only semantic change from the pinned
[Python candidate generator](https://github.com/no-witness-labs/contracts-library/blob/b44b6b0757a75d79b79a4de4712523ee3978760e/formal/scripts/process_blueprint.py#L561)
is replacing `ledgerFuel` (1,000,000 steps) with literal `5000000`. The domains,
context helpers, and negated-acceptance predicate remain the same. The owner
approved the bound after individual experiments on all five vesting obligations.

The Lean unit harness compares its emitted declarations with this fixture.
Namespace and generated-file comments are outside that comparison.

The fixture checks generated statements. The [validation history](../../VALIDATION.md)
records the separate proof evidence and its limits.
