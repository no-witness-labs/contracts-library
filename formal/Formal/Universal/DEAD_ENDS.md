# Universal checks: approaches tried and dropped

Every approach below was tried, and dropped, while building universal checks with Blaster.
Almost all of them failed for one reason: a statement that Blaster has to prove by following the script through a run with many variables does not finish, because the number of paths it has to follow grows with every choice the script makes on a variable.
What was kept is described in `PROPERTIES.md`: checks that the script rejects before it reads the transaction (G1, G2), and checks over shapes of honest transactions written by the validator's author (H1 and H2 for now).

## How Blaster works, and why that matters here

Each check states something about `cekExecuteProgram program args fuel`, which runs the compiled script on the CEK machine for at most `fuel` steps.
Before calling the SMT solver Z3, Blaster unfolds this run step by step, on symbolic input.
When a step depends on a variable, for example on whether a list is empty, Blaster follows each possibility as a separate path.
Only the formula that is left at the end goes to Z3.

Three consequences follow, and every dead end below is an instance of one of them.

1. **The step limit bounds the length of each path, not the number of paths.**
   A path ends when the script halts, fails, or reaches the limit.
   The number of paths is the product of the choices made along the way.
2. **Every variable that the script inspects multiplies the number of paths.**
   A `Credential` has 2 constructors, an `Option` has 2, an `OutputDatum` has 3, a `Data` has 5 at each level, and a list has one possibility per length.
   A transaction in which all of these are variables gives thousands of paths before the script finishes.
3. **Hypotheses do not reduce the number of paths.**
   A statement of the form `h → P` is unfolded in full before Z3 sees `h`.
   For example, assuming `validScriptContext ctx = true` does not stop Blaster from following the paths of transactions that are not valid.

## 1. Generic definitions that take the validator as an argument

**What was tried.**
The checks were written once in `Properties.lean` as generic definitions, such as a definition that takes the validator's `accepts` function as an argument, and then applied to each validator.

**What happened.**
Blaster did not finish on such a statement, even when the definition was an `abbrev`.
The same statement written out in full, with the validator's `accepts` in it directly, was proved.

**What was kept.**
The generator writes every statement out in full in the validator's files.

## 2. `#prep_uplc`

**What was tried.**
The command `#prep_uplc`, from IOG's documented pattern, prepares a script once for later proofs.

**What happened.**
It did not finish on `linear_vesting`, where the `blaster` tactic on the same script did.

**What was kept.**
Only the `blaster` tactic is used.

## 3. Transactions limited to at most 2 items per list

**What was tried.**
Instead of a variable `TxInfo`, each check used a transaction with at most 2 extra inputs, 2 outputs and 2 signatories, each present or absent according to a `Bool`, and with every value holding exactly ada and 2 tokens.
The step limit was lowered to 3,000 (`smallFuel`), and the checks were stated as "every transaction accepted within 3,000 steps satisfies Q".

**Why.**
The intention was that a short step limit and short lists would bound Blaster's work.

**What happened.**
Checks that need the script's accepting run did not finish.
For example, UP-000 for `sale`'s `Buy` (some transaction with redeemer `Buy` is accepted) did not finish, even after the datum and redeemer were given their declared types.

**Why it happened.**
The step limit only bounds the length of each path (consequence 1 above).
The number of paths came from the choices: 27 combinations of list lengths, a credential kind and an optional staking part on each address, 3 kinds of datum on each output, and a variable `Data` wherever a datum or the validity range appeared.

**What was kept.**
Nothing from this approach.

## 4. A lower step limit

**What was tried.**
Lowering the step limit further.

**What happened.**
Nothing changed.
Most paths of `sale` end after 800 to 1,600 steps, well before the limit, so a lower limit removes almost no work (consequence 1 above).

## 5. One `lean` process per check

**What was tried.**
A runner script, `run_checks.py`, wrote each check into its own scratch file and ran `lean` on it with its own time limit.
This kept a check that did not finish from preventing the others from reporting.

**What happened.**
It worked, but each check paid the cost of loading Lean and the validator again, and it made the result depend on an extra layer of scripting.
It was dropped in favour of running one file with one `lean` call.

## 6. A per-check limit with `maxHeartbeats`

**What was tried.**
Lean's option `maxHeartbeats` limits the work spent on one declaration, which would have given each check its own limit inside one file.

**What happened.**
A check with the option set ran well past the point where the limit should have stopped it.
The conclusion was that Blaster's unfolding does not check this limit.
This was not confirmed in Blaster's source code.

## 7. Enumerating transaction structures

**What was tried.**
Each check was generated once for each combination of four choices, 84 combinations in all:

- 0 or 1 extra inputs;
- 0 to 2 outputs, each at a key address or at a script address with an inline datum;
- 0 to 2 signatories;
- a validity range that is unbounded, or bounded at both ends.

Within each combination, the integers, byte strings and hashes were variables.

**What happened.**
Only 7 of the 84 combinations were run, and each took about 2 seconds.
UP-000 found an accepted transaction for `sale`'s `Buy` in the fourth combination (one output to a key address) and for `Cancel` in the third (one signatory).

**Why it was dropped.**

- A result held only for the 84 combinations, and many other choices were fixed in all of them: no address had a staking part, no output had a hashed datum, no value had other than 2 tokens, and every other list was empty.
- Two checks became true for every validator because of these fixed choices: UP-007 (the staking credential is kept), since no address had one, and UP-008 (no more policies than the input), since every value had the same 3 entries.
- `sale` alone had about 2,000 checks.
- It amounted to doing Blaster's case split outside Lean, in Python.

## 8. Weaker statements for every check, for uniformity

**What was tried.**
To treat every check the same way, the purpose and redeemer checks were also stated over the limited transactions at 3,000 steps.

**Why it was dropped.**
Those checks had already been proved in a stronger form: over every transaction, at 1,000,000 steps.
The weaker form gained nothing.
The kept G checks use the stronger form.

## 9. Datum checks with a variable redeemer

**What was tried.**
"A malformed datum is rejected", stated with the redeemer as one variable `Data`, to cover every action in one statement.

**What happened.**
It did not finish on `linear_vesting`.
With the redeemer given each action in turn (`Claim`, `Cancel`), some of the statements did finish.

**Why it happened.**
A variable redeemer includes every valid action, so Blaster had to follow each action's logic, with a variable transaction, before reaching the point where the datum fails.

## 10. Datum checks over every transaction

**What was tried.**
"A malformed datum is rejected" (for each way the datum can fail to decode) and "a spend without a datum is rejected", over every transaction, once per action.

**What happened.**
With Lean checking one proof at a time:

- On `linear_vesting` with `Cancel`, the 4 checks for a datum that is not a constructor were proved, and the next check, a datum with an unknown constructor index, had not finished when the run reached its 2-minute limit.
- On `linear_vesting` with `Claim`, the first datum check had not finished when the run reached its 2-minute limit.
- On `sale` with `Buy`, the datum checks did not finish.

**Why it happened.**
Where the compiled script first reads the datum decides whether it fails early, and the compiled code can differ from the source:

- `sale`'s source takes the datum apart on its first line, but `seller` and `price` are each used once, inside the function given to `list.any`.
  Aiken's optimiser moves a value used once to where it is used, so the compiled script reads the datum only while going through the outputs.
  With a variable transaction, Blaster then follows one path per possible list of outputs before it reaches the datum.
- `VestingDatum` has a single constructor.
  For `Cancel`, the datums that are not a constructor were rejected at once, but the datum with an unknown constructor index was not.
  The likely cause is that the compiled script takes the record apart without checking its constructor index or its number of fields, and reads only the fields it uses.
  This was not confirmed in the compiled script.
  If it is the cause, a datum with the wrong index or an extra field is not rejected at once, and the script continues into the action's logic.

This cannot be known from the blueprint, so the generator cannot know which datum checks will finish.

**What was kept.**
H18 and H19, to be added back, state the same properties on an honest transaction, where the action's logic follows a single path.

## 11. A concrete minimal transaction for the decoding checks

**What was proposed.**
Running each malformed input on one fixed transaction with every list empty, which always finishes, to test whether decoding is strict.

**Why it was not used.**
On `sale`, with no outputs, `Buy`'s `list.any` returns false before it reads the datum.
The check would pass because the transaction is rejected, not because the malformed datum is.
A meaningful fixed transaction has to be one the script would otherwise accept, which is what an honest transaction is.

## 12. Treating a check that does not finish as a finding

**What was proposed.**
Reporting each check that does not finish as evidence of a badly written decoder.

**Why it was not used.**
A check can fail to finish for several unrelated reasons:

- The decoder accepts a malformed value, which would be a real weakness.
- The script reads the transaction before the datum, which is a legitimate design.
- The script checks its arguments early, but the check itself has many branches.
- Blaster's own cost is large.

The run gives no way to tell these apart.

## 13. A summary script over Lean's output

**What was tried.**
`summarise.py` read Lean's log and printed one line per check: proved, finding, error, or no result.

**Why it was dropped.**
It inferred "proved" for any check without an error at its line once the run had ended.
When Lean stopped at line 4 of a file because of a misplaced `set_option`, it reported all 43 checks as proved, although none had been run.
Lean's own output, with Blaster's `✅ Valid` and its `blasterProven` warning at each theorem's line, is shown directly instead.

## 14. Lean checking proofs in parallel

**What happened.**
By default, Lean elaborates the proofs of a file in parallel.
A group of 15 datum checks gave no result within 2 minutes, although one of them, `g3_spend_Cancel_wrongForm_int`, took 3 seconds when run alone.
Running `lean -j1` did not change this.

**What was kept.**
The generated check files set `set_option Elab.async false` after their imports.
Lean then checks one proof at a time, in file order, and prints each result as soon as it is known.
A check that does not finish then delays only the checks after it, and the output shows which check it is.

## 15. A separate file for the honest transactions and their checks

**What was tried.**
The honest transactions and the H checks were generated once into `Formal/Honest/<Validator>.lean`, which was never overwritten afterwards.

**Why it was dropped.**
It split each validator's checks across two folders, and the H checks themselves were then never regenerated.
For a while, the H checks were in the validator's single generated file, after the G checks, but `just blueprint` replaced that file, so honest transactions written into it would have been lost.

**What was kept.**
Each validator has its own folder, given to `just blueprint`.
The generator replaces `Types.lean`, `General.lean` and `Honest.lean` there on every run, and writes `Tx.lean`, which holds the honest transactions, only when it does not exist.
Only the H checks are regenerated; the honest transactions are kept.

## 16. Concrete honest transactions, and honest predicates

**What was tried.**
First, each honest transaction was one concrete value, with H0 (it is valid in the ledger model) and H1 (it is accepted) on it.
Both were proved for `linear_vesting` in 11 seconds.
Then, to cover more transactions, families of transactions were considered, each with a hand-written predicate saying which members are honest, or with the honest predicate taken from the contract's `Spec.lean`.

**Why they were dropped.**
A concrete transaction covers one point, so a pass says little.
A hand-written predicate makes the universal checks depend on the author stating the contract's rules correctly, and taking it from `Spec.lean` makes them depend on the specification, so they are no longer independent of the contract.

**What was kept.**
A shape fixes only the structure of the transaction, and every check uses "valid and accepted" as its hypothesis, so Blaster finds the accepted members itself.
Statements about the contract's rules, such as "only the beneficiary can claim", belong in the hand-written proofs.

## 17. A symbolic currency symbol in a value

**What was tried.**
The `Claim` shape of `linear_vesting` with every leaf symbolic, including the asset's policy and token name.

**What happened.**
Statements that do not mention `validScriptContext` were proved, for example "every accepted member has the beneficiary as signer".
H1 and H2, which mention `validScriptContext`, stopped at once with Blaster's error "Inductive datatype with instance parameters not supported: `Eq`".
With the policy concrete and the token name symbolic, they were proved; with the token name concrete and the policy symbolic, they stopped with the same error.
Which part of the validity rules causes it was not traced; the currency symbols of a value are compared there for sorting and merged when values are added.

**What was kept.**
The policy is a literal in every shape, and the token name is a leaf.
