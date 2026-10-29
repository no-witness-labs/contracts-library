# PR #47 reconciliation

[Issue #39](https://github.com/no-witness-labs/contracts-library/issues/39),
branch `feat/39-developer-workflow`, and
[draft PR #52](https://github.com/no-witness-labs/contracts-library/pull/52)
remain the single workflow delivery. Keep
[PR #47](https://github.com/no-witness-labs/contracts-library/pull/47) open as
the source and comparison baseline until reviewers account for its useful
behavior and the owner approves closure.

This inventory compares PR #47 at
`0dde8ae76e3f8a239bf06685f72327aed4a7c3ef` with the current modular provider.
The original modular checkpoint at `d3bce414a3417b9227fa92f1e0a33672d2829749`
used a 1,000,000-step bound. After semantic review and individual experiments,
the owner approved 5,000,000 steps for UP-001. The [validation history](VALIDATION.md)
keeps the two checkpoints distinct. Full feature parity remains incomplete;
deferred items remain visible gaps in issue #39's acceptance scope.

## Behavior inventory

| Area | PR #47 | Modular prototype | Disposition |
| --- | --- | --- | --- |
| Input selection | Several validators per command; requires a spend handler and `name.name.handler` titles | One validator per request, canonical or unambiguous short name; validates explicit V3 metadata and decodes code | Keep the current Input contract; defer batch orchestration |
| Schema handling | Translates datum and redeemer schemas into bounded symbolic data | Input preserves schemas; UP-001 uses raw redeemer data without schema translation | Review the translation before adding checks that need it |
| Parameters | Rejects any entry with a `parameters` field, including an empty array | Input preserves descriptions; Generator accepts absent or empty lists and rejects nonempty lists | Typed parameter generation is separate work, not behavior supplied by PR #47 |
| Candidate checks | UP-000, UP-001, UP-002, UP-004, UP-005, and UP-011 | UP-001 derived from candidate PR #49 with the reviewed 5,000,000-step bound | Keep the broader UP-001 domains; other providers remain deferred |
| Cases and reachability | Full constructor splits, weaker quick mode, and UNREACHED classification using UP-000 | No schema case splitting or cross-check reachability classification | Review case domains and aggregation before porting spend checks |
| Generated code | Embeds script bytes in the generated Base module; writes modules in the checkout | Embeds script bytes in generated Types; Executor writes to a fresh evidence directory | Retain embedded artifacts and isolated execution |
| Execution | Parallel check modules; default four workers and 600 seconds per check module | Sequential modules under one shared budget, default 30,000 ms; scoped JSON observations | Keep the current Executor contract; defer scheduling and budget options |
| Reports | Expected Valid/Falsified results, witnesses, HOLE/REVIEW labels, waivers, expiry, and off switches | Expected Valid/Falsified results, PASS/FAIL/INCONCLUSIVE, text/JSON summaries, and raw evidence | Keep simple reporting; exceptions and expanded interpretation remain deferred |
| Command options | Generate-only mode, Nix wrapper, preprocessing, and optional removal of validity hypotheses | Prepared checkout and provider selection; pure generation API, without those CLI options | Defer packaging and convenience options; semantic options require review |

The [old generator][old-generator] implements the reference behavior. Current
contracts live in the [Input](Input/README.md), [Generator](Generator/README.md),
[Executor](Executor/README.md), and [Reporter](Reporter/README.md) guides.
The comparison uses source inspection and modular-provider experiments;
PR #47's original proofs were not rerun.

## Reviewed UP-001 scope

The shared property ID does not make the two generated claims interchangeable.

| Question | PR #47 default path | Modular provider |
| --- | --- | --- |
| Redeemer domain | An integer redeemer for each undeclared purpose | Arbitrary raw `Data` |
| Transaction domain | Bounded transaction builders, schema-shaped datums, and purpose-specific witness/redeemer entries | Full `TxInfo` and per-purpose context fields remain open |
| CEK bound | 5,000,000 steps through `Formal.Common` | Literal `5000000`; the shared `ledgerFuel` remains 1,000,000 |
| Meaning of rejection | Negated acceptance within the bound | Negated acceptance within the bound |

Both claims allow fuel exhaustion to satisfy non-acceptance. Neither establishes
an explicit execution error. The modular domain includes every old constructed
context for the five shared purposes: select its transaction, integer redeemer,
and purpose fields as values of the corresponding open context.

At the same bound, this source-level inclusion means the modular claim covers
the old default-path claim for the same supported program and declared handlers.
The inclusion follows from the definitions; no new machine-checked implication
theorem accompanies it. Neither formula adds a ledger-validity premise; a failing
witness needs review before assigning an on-chain consequence.

The [old acceptance predicates][old-predicates], [current provider][new-provider],
and [current context helpers][new-contexts] pin the relevant definitions. PR #47's
optional `--prep` path has separate execution predicates and also needs review
before reuse. Its `--quick` option restricts schema choices. `--no-validity`
changes spend-check hypotheses but does not affect UP-001, which has no validity
premise.

The original [validation baseline](VALIDATION.md) compares the modular path
with candidate PR #49 at 1,000,000 steps. The later individual experiments all
returned Valid at 5,000,000 steps on the same vesting artifact. Those results
support the stated bounded claims; they do not establish full PR #47 parity.

## Work split and next checkpoint

| Stage | Scope | Status |
| --- | --- | --- |
| Light documentation | Inventory retained behavior, deferred features, and semantic differences | Recorded here |
| Heavy semantic review | Compare UP-001 statements, domains, bounds, and assumptions; check each purpose separately | Completed; the owner approved the 5,000,000-step bound |
| Scoped implementation | Update the UP-001 provider, scope text, and fixtures; validate the complete workflow | Implemented; all five checks passed in the complete workflow at 5,000,000 steps |

Remaining work includes the deferred behavior above and review of the supported
workflow with Irfan. Reconcile further behavior one checkpoint at a time,
preserving source attribution. PR #47 closure and issue #39 acceptance remain
owner decisions.

[old-generator]: https://github.com/no-witness-labs/contracts-library/blob/0dde8ae76e3f8a239bf06685f72327aed4a7c3ef/formal/scripts/GenUniversalChecks.lean
[old-predicates]: https://github.com/no-witness-labs/contracts-library/blob/0dde8ae76e3f8a239bf06685f72327aed4a7c3ef/formal/Formal/Common.lean
[new-provider]: Generator/OtherPurpose.lean
[new-contexts]: https://github.com/no-witness-labs/contracts-library/blob/d3bce414a3417b9227fa92f1e0a33672d2829749/formal/Formal/Universal/Properties.lean
