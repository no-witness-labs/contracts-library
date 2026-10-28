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

## Proposed interface

| Part | Proposal |
| --- | --- |
| Request | Existing blueprint and a validator selection |
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
- Adding an unrelated validator does not change an existing selection.
- Missing or ambiguous selections produce a clear error.
- A blueprint without compiled code cannot satisfy the initial input contract.
- Malformed content or inconsistent code across a selected validator's handlers
  produces a clear error.
- Unsupported formats or features produce an explicit result.
- A blueprint declaring another Plutus version produces an unsupported result.
- Reading an artifact preserves its source bytes.

## Still to decide

- The supported blueprint feature profile and missing-version behavior.
- Parameter handling and the distinction between descriptions and applied code.
- Whether each request selects exactly one validator.
- Compiled-code decoding and validation requirements.
- The common metadata representation and error types.

These examples and interface details remain proposals. No component
implementation or test suite accompanies this document yet.
