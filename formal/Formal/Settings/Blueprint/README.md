# UP-016: mint quantity

Draft for [issue #37](https://github.com/no-witness-labs/contracts-library/issues/37).
The Lean modules are uncompiled and unexecuted. The rejection and applicability
statements are `Prop` definitions, not proved theorems.

The Settings Mint example has one seed input and two outputs. The mutation
increases the existing token quantity from `1` to `1 + delta` and credits
`delta` to output 1. Output 0 stays unchanged. The proposed claim requires positive
`delta`, a valid accepted original context, and a valid changed context.
Rejection excludes exhaustion of the 1,000,000-step CEK bound.

This fixes the parameter instance and transaction structure. ADA amounts, fee,
time, and the integer-valued current datum stay symbolic. Other datum forms,
transaction sizes, burns, and new token names are outside this draft.

## Snapshot

[Validator metadata](validator-metadata.json) records the exact upstream source,
raw `.ak` file hash, applied CBOR, compiler, and serialized parameters. Source:
[IO commit `96c9f32`](https://github.com/input-output-hk/contracts-library/commit/96c9f328060b1664402134d71fdf0bc4a838fba7).
These are synthetic test parameters, in application order:

| Parameter | Value |
| --- | --- |
| Seed reference | Transaction ID byte `11` repeated 32 times; index `0` |
| Proposer key | Byte `22` repeated 28 times |
| Apply key | Byte `33` repeated 28 times |
| Apply delay | `60000` ms |
| Token name | UTF-8 `UP016` |

Byte values above are hexadecimal. Applied Plutus V3 policy hash:
`50dc52e6bf8db417d8e5b70bbd2c1caa6a45a5ca7854a51d99b63e60`.
CBOR-byte SHA-256:
`527f551e2b615d50ce44679e9bc585552cac8c549a0637864eb93e4c34f2ec50`.

## Prepare the ignored script file

From the repository root, materialize the exact recorded bytes:

```sh
python3 - <<'PY'
import json
from pathlib import Path
metadata = json.loads(Path("formal/Formal/Settings/Blueprint/validator-metadata.json").read_text())
script = Path("formal/Scripts/UP016/settings.settings.cbor")
script.parent.mkdir(parents=True, exist_ok=True)
script.write_text(metadata["cbor_hex"] + "\n")
PY
```

Run later Lean commands from `formal/`. `Types.lean` imports this file;
`Tx.lean` defines the shape and mutation; `MintQuantity.lean` contains the
proposed statements and an explicit concrete-control runner. No solver or
concrete evaluation starts automatically. Compilation, concrete controls, and
symbolic proofs remain pending.

Types and evaluator predicates come from the existing blueprint generator at
[`6c2bd75`](https://github.com/no-witness-labs/contracts-library/blob/6c2bd759e7fb1332991210f88fcf748ec2d4e72c/formal/scripts/process_blueprint.py),
with shared source from #44.
This candidate adds the Settings shape
and quantity mutation; it does not modify that generator.
