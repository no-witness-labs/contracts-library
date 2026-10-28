# Executor controls

`outcomes.lean.txt` is source data for a real Lean/Blaster integration test.
It contains a valid equation and an intentionally false equation. The compiler
should report Valid for `good` and Falsified for `bad`, with exit code one
because the latter theorem fails.

The integration harness writes this source to its own execution workspace.
These are arithmetic controls for diagnostic attribution, not properties of a
Cardano validator. Their observations retain Blaster's SMT trust boundary.
