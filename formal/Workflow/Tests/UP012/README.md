# UP-012 vesting workflow scenario

[Candidates/UP012.lean](../../../Candidates/UP012.lean) owns the single source of
the four original propositions from [PR #55](https://github.com/no-witness-labs/contracts-library/pull/55)
at `f5cbda7df624f2496dd2e6fe354a0cd15365b923`. [Profile.lean](Profile.lean) supplies
the original vesting types, transaction shapes, and pinned artifact guard.

From `formal/`:

```sh
lake exe workflow_up012_tests
```

The suite uses the public CLI and expects Valid for Claim signer removal,
Claim applicability, Cancel signer removal, and Cancel applicability. It also
checks explicit rejection of an unsupported artifact. Generated files and
reports stay under `formal/output/`.

## Scope and fixtures

The profile remains restricted to the original unparameterized vesting artifact.
Its supplied Claim and Cancel shapes each have one signer; the operation removes
the first key. The original bound is 1,000,000 steps, and `rejectedWithin` requires
an error or non-unit halt within the bound. Exhaustion does not establish rejection.
Both applicability statements remain separate required jobs.

`Inputs/plutus.json` is a self-contained selection of the vesting entries and
supporting schemas from the repository's `onchain/plutus.json`. It preserves the
compiled code and selected handler metadata. `Inputs/compiled-code.txt` and
`Expected/declarations.lean.txt` are the unchanged independent regression oracles.
`Inputs/unsupported.json` exercises the profile guard.

The source templates retain original comments for provenance. Runtime generation
uses the Lean profile and candidate module. General required-signer semantics
remain outside this experimental scenario, as tracked in issue #33.
