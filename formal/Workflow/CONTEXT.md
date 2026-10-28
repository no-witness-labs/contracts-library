# Workflow language

Terms for the reusable checking workflow. The initial target scope is validators.

## Language

**Check target**:
The subject selected for property checking. The first supported kind is a
validator; other kinds require an explicit extension of the contract.

**Target description**:
The common description of a check target, its compiled artifact, and the
interface metadata available for generating checks.

**Input artifact**:
The supplied document or serialized program that describes a target. An input
format and a target kind are separate concepts.

**Blueprint**:
A [CIP-57](https://cips.cardano.org/cip/CIP-57) document describing validators
and their interfaces, with optional compiled script content.

**Script CBOR**:
The serialized compiled Plutus code carried by a supported input representation.
This term identifies an encoding concern, rather than an additional target kind.

**Check job**:
A generated obligation with its declared expectation and scope, together with
the information needed to execute it and interpret the observations.
