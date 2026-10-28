# Input component

Input's Lean implementation selects one validator, validates its embedded
compiled code, and preserves the metadata Generator needs. The
[workflow decisions](../README.md) define its scope.

## Use and test

With the repository's pinned Lean dependencies prepared, run from `formal/`:

```sh
lake build Workflow workflow_input_tests
lake exe workflow_input_tests
```

Import `Workflow.Input` to use:

- `Workflow.Input.parse source selector`: read blueprint text and return an
  `Except Error InputResult`.
- `Workflow.Input.read path selector`: read a file and return the same result
  in `IO`, preserving the input file.

`InputResult.target` is Generator's handoff. It contains the canonical name,
explicit Plutus version, original encoded code, handler descriptions, ordered
parameter descriptions, and optional schema definitions and compiler metadata.
`sourceText` and `sourcePath` retain provenance separately. Input decodes the
program internally for validation; it does not expose a decoded program field.

## Supported blueprint profile

The first adapter supports the current Aiken-style Plutus V3 blueprint layout:

- The document contains a `preamble` object with explicit `plutusVersion: "v3"`
  and a `validators` array.
- Each entry has a `module.validator.handler` title. Module paths can contain
  `/`. Select the full `module.validator` name or an unambiguous short name.
- Entries for one validator share the exact encoded `compiledCode` and parameter
  descriptions. Duplicate handlers and inconsistent entries produce errors.
- Supported purposes are `spend`, `mint`, `withdraw`, `publish`, `vote`, and
  `propose`. Input retains the `else` fallback separately from declared purposes.
- A declared handler requires a redeemer description. Datum descriptions are
  optional. Each supplied argument description contains a schema object.
- Optional parameters remain absent or retain their declared order. Input does
  not apply values. An explicit empty array remains distinct from absence.
- Optional definitions and compiler metadata are objects when present.
  Optional titles, descriptions, and declared hashes are strings when present.

This profile does not cover every CIP-57 blueprint layout. Unsupported title
profiles and selected handler purposes produce explicit errors. Input preserves
schema JSON and definitions without translating types or validating the full
schema vocabulary; Generator owns translation and reports unsupported schemas.

## Compiled-code validation

Input uses the pinned PlutusCoreBlaster dependency's error-returning
[`singleCborEncodedScriptFromHex?` helper](https://github.com/input-output-hk/PlutusCoreBlaster/blob/4ef48606303c45225d3ed2e2a87fc50280a763b7/PlutusCore/UPLC/ScriptEncoding/Basic.lean#L67).
The helper decodes hexadecimal, Concise Binary Object Representation (CBOR), and
the serialized Plutus program. Input also uses the existing CBOR decoder to
reject bytes trailing after the encoded script.

Success requires successful decoding. Input neither executes the validator nor
runs a solver. It preserves supplied code and declared hashes without applying
parameters or checking correspondence to source code or metadata claims.

## Errors and metadata

Errors contain a category, field path, and explanation. Categories distinguish
malformed JSON, missing fields, malformed fields, unsupported input, selection
errors, inconsistent handlers, decoding errors, and file errors.

Missing required fields produce an error. Optional fields remain absent without
guessed values; an explicit null is not an omitted field. Schema content stays
declarative. A successful read does not establish that a selected Generator can
support every schema or parameter configuration.

## Test boundary

The native Lean fixture harness checks selection, multiple validators and
purposes, module paths, parameter order, absent versus empty metadata, source
preservation, file errors, and malformed inputs. It includes invalid hex,
truncated CBOR, rejected programs, and trailing bytes. These tests use no Aiken
build, property generator, or solver.

The fixture's compiled program is a small decoding example from the dependency's
script-encoding tests. It is not evidence of a validator's behavior. Read-only
smoke checks also succeeded on the repository blueprint's linear-vesting,
settings, and DAO-proposal entries, including their parameter descriptions.

Standalone CBOR files, function targets, other Plutus versions, and additional
blueprint profiles remain later extensions. Generator, Executor, and Reporter
integration follows this Input checkpoint.
