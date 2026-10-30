# Universal-property candidates

This category contains maintained candidates for reusable validator checks.
The name describes the intended reuse; it does not establish that every property
applies to every validator, model, or protocol.

| Code | Primary claim | Folder |
| --- | --- | --- |
| UP-001 | Nonacceptance over the configured context family | [UP001](UP001/README.md) |
| UP-012 | Experimental signer-removal rejection with explicit premises | [UP012](UP012/README.md) |

[Index.lean](Index.lean) imports the definitions and points to their metadata.
Each folder has one primary definition, metadata, and a README. Concrete check
bindings select the model, evaluator predicates, bounds, and supported target.
