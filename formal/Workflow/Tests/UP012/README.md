# UP-012 vesting workflow scenario

[UP012/Definition.lean](../../../Formal/Properties/Universal/UP012/Definition.lean)
owns the shared signer-removal statement and applicability predicate.
[Candidates/UP012.lean](../../../Candidates/UP012.lean) instantiates them for Claim
and Cancel, preserving the four claims from PR #55 at
`f5cbda7df624f2496dd2e6fe354a0cd15365b923`. [Profile.lean](Profile.lean) supplies
the pinned artifact guard and imports the native types/models from Formal/TxModels.

From `formal/`:

```sh
lake exe workflow_up012_tests
```

The suite uses the public CLI and expects Valid for Claim signer removal,
Claim applicability, Cancel signer removal, and Cancel applicability. It also
checks explicit rejection of an unsupported artifact. Generated files and
reports stay under `formal/output/`.

The [negative control](NegativeControl.lean) runs the four component APIs with
the same validator and model, but retains the signer in the generated checks.
The solver must report Falsified/FAIL for both removal obligations and Valid/PASS
for both applicability obligations. The control report must say FAIL/1. These intentional
failures make the enclosing test suite succeed; a timeout or inconclusive result
fails the suite. The control has its own test-only label and is not a CLI candidate.
It leaves the actual candidate, artifact guard, and model unchanged.

## Scope and fixtures

The profile remains restricted to the original unparameterized vesting artifact.
Its supplied Claim and Cancel shapes each have one signer; the operation removes
the first key. The original bound is 1,000,000 steps, and `rejectedWithin` requires
an error or non-unit halt within the bound. Exhaustion does not establish rejection.
Both applicability statements remain separate required jobs.

The generated `Tx.lean` imports and aliases the native Claim and Cancel models,
including their inputs, outputs, and signer.
Blueprint schemas describe datum and redeemer encoding; they do not determine
those transaction contexts. These remain experimental test models. Other
providers can supply different models or use generic contexts, as UP-001 does.

`Inputs/plutus.json` is a self-contained selection of the vesting entries and
supporting schemas from the repository's `onchain/plutus.json`. It preserves the
compiled code and selected handler metadata. `Inputs/compiled-code.txt` and
`Expected/legacy-declarations.lean.txt` are the frozen independent regression oracles.
The current declarations fixture records applications of the shared definition;
DefinitionEquivalence.lean checks their equivalence to the expanded formulas.
`Inputs/unsupported.json` exercises the profile guard.

Generated headers identify the current Lean emitter and the original PR/SHA
provenance. Runtime generation uses the profile and candidate module. Edit the
native model and rerun to change the generated scenario sources.
General required-signer semantics
remain outside this experimental scenario, as tracked in issue #33.
