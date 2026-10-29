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

## UP-012 fixtures

`up012-compiled-code.txt` identifies the pinned vesting artifact accepted by the
experimental UP-012 profile. `up012-declarations.txt` contains the four original
propositions from [PR #55's DropSigner.lean](https://github.com/no-witness-labs/contracts-library/blob/f5cbda7df624f2496dd2e6fe354a0cd15365b923/formal/Formal/Vesting/Linear/Blueprint/DropSigner.lean).
The unit harness compares the emitted job propositions with that fixture.

The provider's source templates preserve the same revision's `Types.lean`,
`Tx.lean`, and `DropSigner.lean`. Only namespace/import paths and compiled-script
loading adapt to the workflow. Their 1,000,000-step bound and first-signer
operation remain intact. The fixtures are source comparisons, not proof results.
