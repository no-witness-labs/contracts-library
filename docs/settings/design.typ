#import "../diagrams-template.typ": *

#show: report

Reference Settings at IO commit `42048b7`. The figures show withdrawals for
script authorization. Key authorization uses an extra signer.

= Launch settings

#let launch_tx = vanilla_transaction(
  "",
  inputs: (
    (
      name: "Seed UTxO",
      // wallet: true,
      // address: "creator_addr",
      // value: ("ADA": "min_ada", "SetupFeeAsset": "s"),
    ),
  ),
  mint: (
    "Settings NFT": 1,
  ),
  withdrawals: (
    "apply_auth",
  ),
  outputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        "ADA": "funded",
      ),
      datum: (
        current: [*data*],
        next: [None],
        next_apply: [None],
      ),
    ),
  ),
  notes: [
    - `settings_addr`: payment is `settings_hash`, staking is any (chosen at launch)
    - continuations must reproduce the spent input's full address, so the staking key cannot be changed once deployed
    - `settings_nft`: policy is `settings_hash`, token name is `settings_token_name`
    - `settings_hash = hash(settings_validator(seed_utxo, propose_auth, apply_auth, apply_delay, settings_token_name))`
    - `out_ix` selects the output with an inline datum and no reference script.
  ],
)

#figure(launch_tx, caption: [Launch settings transaction]) <fig:launch>


= Propose settings

#let propose_tx = vanilla_transaction(
  "",
  inputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        // "ADA": "min_ada",
      ),
      datum: (
        // current: "Data",
        // next: "Option(Data)",
        current: [data],
        next: [maybe_data],
        next_apply: [maybe_timestamp],
      ),
    ),
  ),
  withdrawals: (
    "propose_auth",
  ),
  validRange: (
    "lower": [`since_slot`],
    "upper": [`until_slot - 1`],
  ),
  outputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        // "ADA": "min_ada",
      ),
      datum: (
        // current: "Data",
        // next: "Option(Data)",
        current: [data],
        next: [*Some(proposed)*],
        next_apply: [*Some(timestamp)*],
      ),
    ),
  ),
  notes: [
    - `settings_addr`: payment is `settings_hash`, staking is unchanged
    - `settings_nft`: policy is `settings_hash`, token name is `settings_token_name`
    - `settings_hash = hash(settings_validator(seed_utxo, propose_auth, apply_auth, apply_delay, settings_token_name))`
    - `maybe_data`: can be `None` or `Some(data)`
    - The output at `out_ix` keeps the full input address and all non-ADA assets. It carries at least the input's ADA, an inline datum, and no reference script.
    - The new pending value differs from `current`.
    - The timing check requires a finite upper bound. In this example it is the start of the exclusive `until_slot` in POSIX milliseconds.
    - The pending deadline `timestamp` is at least that upper bound plus `apply_delay`.
  ],
)

#figure(propose_tx, caption: [Propose settings transaction]) <fig:propose>


= Apply settings

#let apply_tx = vanilla_transaction(
  "",
  inputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        // "ADA": "min_ada",
      ),
      datum: (
        // current: "Data",
        // next: "Option(Data)",
        current: [data1],
        next: [Some(data2)],
        next_apply: [Some(timestamp)],
      ),
    ),
  ),
  withdrawals: (
    "apply_auth",
  ),
  validRange: (
    "lower": [`since_slot`],
  ),
  outputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        // "ADA": "min_ada",
      ),
      datum: (
        // current: "Data",
        // next: "Option(Data)",
        current: [*data2*],
        next: [*None*],
        next_apply: [*None*],
      ),
    ),
  ),
  notes: [
    - `settings_addr`: payment is `settings_hash`, staking is unchanged
    - `settings_nft`: policy is `settings_hash`, token name is `settings_token_name`
    - `settings_hash = hash(settings_validator(seed_utxo, propose_auth, apply_auth, apply_delay, settings_token_name))`
    - The finite lower bound is the start of `since_slot` in POSIX milliseconds. It must be at or after `timestamp`.
    - The output at `out_ix` keeps the full input address and all non-ADA assets. It carries at least the input's ADA, an inline datum, and no reference script.
  ],
)

#figure(apply_tx, caption: [Apply settings transaction]) <fig:apply>


= Close settings

#let close_tx = vanilla_transaction(
  "",
  inputs: (
    (
      name: "Settings UTxO",
      address: "settings_addr",
      value: (
        "Settings NFT": "1",
        // "ADA": "min_ada",
      ),
    ),
  ),
  mint: (
    "Settings NFT": -1,
  ),
  withdrawals: (
    "apply_auth",
  ),
  notes: [
    - `settings_addr`: payment is `settings_hash`, staking is any
    - `settings_nft`: policy is `settings_hash`, token name is `settings_token_name`
    - `settings_hash = hash(settings_validator(seed_utxo, propose_auth, apply_auth, apply_delay, settings_token_name))`
    - `Close` requires an authorized spend and one negative entry under the policy. The `Burn` mint handler requires one entry of quantity `-1`.
    - The close helper reads no datum fields and requires no continuation.
  ],
)

#figure(close_tx, caption: [Close settings transaction]) <fig:close>
