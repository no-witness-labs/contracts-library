# Input contract

Design status: the owner confirmed the initial target, input format, and Plutus
version. The detailed interface, supported features, and implementation still
need review.

## Agreed scope

The initial target is a Plutus V3 validator supplied through a blueprint
containing its compiled code. Standalone CBOR plus metadata, other Plutus
versions, and function targets remain later extensions. The
[workflow decisions](../README.md) own these scope choices.

Input reads the artifact and returns a target description. Blueprint-format
knowledge belongs here; downstream components use the common description.
Input does not generate checks, apply property-specific assumptions, or run
proofs.

The same Input component reads validators within the supported blueprint profile,
independently of property selection. Validator-specific content changes its
returned description. Choosing a different property for the same artifact and
validator does not change that description.

## Selection

Each Input request selects exactly one validator and returns one target
description. The caller can repeat requests to process several validators.

The selection must identify a unique validator. A missing or ambiguous match
produces an explicit error rather than silently selecting the first entry.

## Parameters

Input reads validators with or without declared parameters. It preserves the
parameter descriptions and their order without applying values or rewriting the
compiled artifact.

Generator determines how each selected check uses those parameters. A generator
that cannot support the requested parameter handling must report that limitation
explicitly. Successful input reading does not establish generator support.

## Missing metadata

Missing required metadata produces a clear input error. The first input profile
requires an explicit Plutus V3 declaration; Input must not assume V3 when the
version is absent.

Missing optional metadata stays absent. Input must not fill it with guessed
types, purposes, or other values. Keep absent metadata distinguishable from an
explicit empty value. The complete required-field list remains part of the
blueprint profile review.

## Compiled-code decoding

Input uses the existing Lean decoder to check that the embedded compiled code
decodes into a Plutus program. The helper decodes hexadecimal and Concise Binary
Object Representation (CBOR) before decoding the serialized program. Any
decoding failure produces a clear input error. Input checks structure without
executing the validator or invoking a solver.

The pinned PlutusCoreBlaster dependency provides the error-returning
[`singleCborEncodedScriptFromHex?` helper](https://github.com/input-output-hk/PlutusCoreBlaster/blob/4ef48606303c45225d3ed2e2a87fc50280a763b7/PlutusCore/UPLC/ScriptEncoding/Basic.lean#L67).
Reuse that decoding path and preserve the supplied artifact. Supporting a
standalone CBOR file remains a separate, deferred input extension.

Source inspection established the reuse path. The new component integration
still needs compilation and fixture checks. Confirm the accepted encoding
profile, decoder behavior, and error mapping before implementation.

## Proposed interface

| Part | Proposal |
| --- | --- |
| Request | Existing blueprint and a selection identifying exactly one validator |
| Success | Selected validator's identity, compiled artifact, available interface metadata, and source snapshot identity |
| Error | Explicit missing, malformed, ambiguous, inconsistent, or unsupported input |
| Source ownership | Preserve the supplied blueprint unchanged |

The target description must distinguish supplied metadata from missing
information. It must not infer a declared purpose or argument type merely from
the presence of compiled bytes. The exact representation still needs review.

## Isolated test environment

Use small blueprint fixtures with varied validator names and schemas. Tests
exercise Input without a property generator, Aiken build, or proof tool.

Proposed acceptance examples:

- A valid selection returns the corresponding compiled artifact and metadata.
- A blueprint with several validators still returns only the selected target.
- Adding an unrelated validator does not change an existing selection.
- Missing or ambiguous selections produce a clear error.
- A blueprint without compiled code cannot satisfy the initial input contract.
- Valid embedded code decodes through the reused Lean helper.
- Invalid hex, malformed CBOR, and decoder-rejected programs produce clear input
  errors.
- Malformed content or inconsistent code across a selected validator's handlers
  produces a clear error.
- Unsupported formats or features produce an explicit result.
- A blueprint declaring another Plutus version produces an unsupported result.
- A blueprint without an explicit Plutus version produces a clear input error.
- Missing optional metadata remains absent without invented values.
- Parameterized fixtures retain their parameter descriptions in the declared
  order, without applying values.
- Choosing another property for the same input leaves its target description
  unchanged.
- Reading an artifact preserves its source bytes.

## Still to decide

- The supported blueprint feature profile and complete required-field list.
- The representation of parameter descriptions and missing parameter metadata.
- The accepted compiled-code encoding profile and decoder error mapping.
- The common metadata representation and error types.

These examples and interface details remain proposals. No component
implementation or test suite accompanies this document yet.
