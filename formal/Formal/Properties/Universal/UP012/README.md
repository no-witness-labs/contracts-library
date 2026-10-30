# UP-012: experimental signer-removal rejection

[Definition.lean](Definition.lean) contains one primary `statement` and its
supporting `applicability` predicate. They take a transaction-context family and
the validity/acceptance/rejection predicates used by a configured check.

The statement quantifies over the model's inputs. If the original context passes
the supplied validity predicate, is accepted, has a nonempty signer list, and the
context with its first signer removed also passes that predicate, the changed
context must be rejected. Applicability requires a witness to those premises.

The existing bindings use TxM-007 (Claim) and TxM-008 (Cancel), the model's
`validScriptContext` predicate, and explicit rejection within 1,000,000 CEK steps.
The runtime profile retains its pinned linear-vesting artifact guard. These are
two applications of one property, with separate applicability obligations.

The current models contain one signer, so the change removes the sole signer.
The check does not identify which signatures a protocol should require or
establish general authorization correctness. Property redesign remains issue #33.
The property-bank metadata and index migration is tracked by issue #76.
