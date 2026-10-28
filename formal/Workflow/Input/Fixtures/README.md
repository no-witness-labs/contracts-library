# Input fixture

`blueprint.json` is a synthetic metadata fixture with two validator identities,
multiple handler entries, ordered parameters, and schema references.

The compiled code, `480100002221200101`, comes from `test1` in the pinned
[PlutusCoreBlaster script-encoding tests](https://github.com/input-output-hk/PlutusCoreBlaster/blob/4ef48606303c45225d3ed2e2a87fc50280a763b7/PlutusCore/UPLC/ScriptEncoding/Tests.lean#L12).
It is a small decodable program used to test parsing and metadata preservation.
The fixture does not demonstrate acceptance, rejection, or proof of a validator
property.
