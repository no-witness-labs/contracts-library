import Universal.Demo.Vault.Base
import Universal.Demo.Vault_buggy.Base
import Universal.Demo.Linear_vesting.Base

/-!
Regression test: one file importing every validator's `Base`. It builds only if no two
validators declare the same global name (`#prep_uplc`, behind `--prep`, declares its name outside
any namespace). Add a line here when a validator is added.
-/
