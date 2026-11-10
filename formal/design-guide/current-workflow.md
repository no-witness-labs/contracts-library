# Current workflow

UP-012 example. We maintain the property, models, and generation code;
the tool creates the verification harness for each run.

```mermaid
flowchart TD
    P["MANUAL: property rule<br/>UP012/Definition.lean"]
    M["MANUAL: models and data types<br/>TxM007.lean / TxM008.lean<br/>VestingTypes.lean"]
    I["CLIENT INPUT<br/>plutus.json<br/>Pinned vesting validator"]

    P --> G
    M --> G
    I --> G

    G["MANUAL: generation code<br/>Candidates/UP012.lean<br/>UP012/Profile.lean"]
    G -->|Automatically writes| H

    H["GENERATED: Lean verification harness<br/>Types.lean: validator and evaluation<br/>Tx.lean: model references<br/>Checks.lean: property applications"]
    H --> V["AUTOMATIC EXECUTION<br/>Workflow/App/Verification.lean<br/>Runs Lean and Blaster"]
    V --> R["GENERATED RESULT<br/>check-result.json"]
```

`Tx.lean` imports our model definitions. This UP-012 profile accepts only
the pinned vesting artifact.

Sources: [property](../Formal/Properties/Universal/UP012/Definition.lean),
[Claim model](../Formal/TxModels/Definitions/TxM007.lean),
[Cancel model](../Formal/TxModels/Definitions/TxM008.lean),
[data types](../Formal/TxModels/VestingTypes.lean),
[check adapter](../Candidates/UP012.lean),
[profile](../Workflow/Tests/UP012/Profile.lean), and
[verification](../Workflow/App/Verification.lean).
