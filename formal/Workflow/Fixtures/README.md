# CLI demo fixtures

`plutus.json` contains two unparameterized Plutus V3 validators:

| Selector | Intended UP-001 outcome | Fixture behavior |
| --- | --- | --- |
| `vault.vault` | PASS | The fallback rejects undeclared purposes |
| `vault_buggy.vault_buggy` | FAIL | The fallback accepts undeclared purposes |

The blueprint, Aiken source files, `aiken.toml`, and `aiken.lock` preserve the
exact contents of [PR #47's demo project](https://github.com/no-witness-labs/contracts-library/tree/0dde8ae76e3f8a239bf06685f72327aed4a7c3ef/formal/Universal/Demo/aiken)
at `0dde8ae76e3f8a239bf06685f72327aed4a7c3ef`. They retain that project's
Apache-2.0 license and source attribution. The blueprint records Aiken
`v1.1.19+e525483`; this checkpoint uses that compiled snapshot without rebuilding it.

Blueprint SHA-256:
`afd375487a56be74f83f60e7c94fc2008f6e79b418a7bde3f1575bb4c6c9b426`.

`invalid-code.json` is a local input-error fixture. Its metadata identifies a
spend handler, but `compiledCode` contains non-hexadecimal text. Input must reject
it before execution, producing INCONCLUSIVE with exit code 2.

These fixtures exercise the assembled workflow. PASS covers the stated UP-001
scope, not general safety of the vault. Use the [quickstart](../QUICKSTART.md)
for the exact commands and output locations.
