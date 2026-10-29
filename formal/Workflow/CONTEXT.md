# Workflow language

Terms for the reusable checking workflow. The initial target scope is validators.

## Language

**Check target**:
The subject selected for property checking. The first supported kind is a
validator; other kinds require an explicit extension of the contract.

**Target description**:
The common description of a check target, its compiled artifact, and the
interface metadata available for generating checks.

**Parameter description**:
The declared interface metadata for a validator's configuration arguments,
including their order. It describes the arguments without applying values.

**Input artifact**:
The supplied document or serialized program that describes a target. An input
format and a target kind are separate concepts.

**Blueprint**:
A [CIP-57](https://cips.cardano.org/cip/CIP-57) document describing validators
and their interfaces, with optional compiled script content.

**Script CBOR**:
The serialized compiled Plutus code carried by a supported input representation.
This term identifies an encoding concern, rather than an additional target kind.

**Property**:
A statement about a target's behavior.

**Candidate property**:
A proposed property whose definition and intended use remain under review.

**Transaction model**:
The transaction contexts, variable values, and constraints covered by a check.
A model can support several properties, and a property can use several models.

**Check variant**:
A particular version of a property definition paired with a transaction model
and its stated assumptions and limitations.

**Check job**:
A generated obligation with its declared expectation and scope, together with
the information needed to execute it and interpret the observations.

**Check definition**:
The property statement, model assumptions, applicability conditions, and expected
observations that specify a check.

**Applicability obligation**:
An obligation establishing that the scenario required by a property check exists
within its stated model. Its result qualifies the associated property obligation.

**Candidate catalogue**:
Named references to maintained candidate check definitions and their supporting
models.

**Run selection**:
The checks included in one workflow execution by its configured defaults or
optional enable/disable choices.

**Workflow test scenario**:
A prepared combination of candidate references, target inputs, scenario models,
and expected outcomes used to test the assembled workflow.

**Check provider**:
An ordinary Lean function supplying property-specific generation through the
common Generator contract.

**Generation plan**:
The generated modules, check jobs, and scope notes for a selected target. A plan
without obligations records that state explicitly and carries no passing verdict.

**Job observation**:
The solver result and diagnostics attributed to one generated job. An observed
result and its declared expectation remain separate until reporting.

**Execution evidence**:
The retained sources, compiler logs, process metadata, and job observations for
one execution attempt.

**Check report**:
The comparison of requested jobs' expectations with their execution
observations, preserving each check's scope and incomplete outcomes.
