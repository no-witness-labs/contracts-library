import Universal.Demo.Vault.Base
import Universal.Demo.Vault_buggy.Base
import Universal.Demo.Linear_vesting.Base

/-!
Regression test: one file importing every validator's `Base`. It builds only if no two
validators declare the same global name (`#import_uplc` and `#prep_uplc` declare theirs outside
any namespace). Add a line here when a validator is added.
-/
