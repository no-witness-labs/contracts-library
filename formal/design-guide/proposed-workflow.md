# Proposed workflow

Proposal for discussion. Expand the adapter to support compatible validator
interfaces, using our reviewed property and model libraries.

```mermaid
flowchart TD
    P["MANUAL: reusable property library<br/>UP012/Definition.lean"]
    M["MANUAL: reviewed model library<br/>TxM007.lean / TxM008.lean<br/>Additional models when needed"]
    I["CLIENT INPUT<br/>plutus.json<br/>A compatible validator"]

    P --> G
    M --> G
    I --> G

    G["MANUAL: adapter code, PROPOSED CHANGES<br/>Candidates/UP012.lean: expand<br/>scripts/process_blueprint.py: integrate"]
    G -->|Automatically writes| H

    H["GENERATED: small Lean harness<br/>Types.lean: translated validator interface<br/>Tx.lean: selected model references<br/>Checks.lean: selected property applications"]
    H --> V["AUTOMATIC EXECUTION<br/>Workflow/App/Verification.lean<br/>Runs Lean and Blaster"]
    V --> R["GENERATED RESULT<br/>check-result.json"]
```

The library separation already exists. The proposed change replaces pinned
scenario wiring with a reusable adapter and integrates blueprint type translation.
Only compatible, reviewed property/model/validator combinations would run.

Existing code to reuse or extend: [property](../Formal/Properties/Universal/UP012/Definition.lean),
[models](../Formal/TxModels/Index.lean),
[adapter](../Candidates/UP012.lean),
[type translator](../scripts/process_blueprint.py), and
[verification](../Workflow/App/Verification.lean).
