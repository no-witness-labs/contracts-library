"""Stdlib-only regression tests for the blueprint type/CBOR foundation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "process_blueprint.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "blueprint-foundation.json"
SPEC = importlib.util.spec_from_file_location("blueprint_foundation", SCRIPT)
BLUEPRINT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BLUEPRINT
SPEC.loader.exec_module(BLUEPRINT)


class BlueprintFoundationTests(unittest.TestCase):
    def setUp(self):
        self.blueprint = json.loads(FIXTURE.read_text())

    def generated(self, blueprint=None):
        lines, info = BLUEPRINT.generate(
            self.blueprint if blueprint is None else blueprint,
            "example", "Formal.Fixture.Blueprint", "Scripts"
        )
        return "\n".join(lines + [f"end {info.prefix}"]) + "\n"

    def cli(self, root, *args, blueprint=None):
        path = Path(root) / "plutus.json"
        path.write_text(json.dumps(self.blueprint if blueprint is None else blueprint))
        return subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), str(path), "example", *args],
            cwd=root, capture_output=True, text=True, timeout=30
        )

    def test_named_types_and_isdata(self):
        source = self.generated()
        self.assertIn("structure Fixture.Types.Datum where", source)
        self.assertIn("inductive Fixture.Types.Redeemer where", source)
        self.assertIn("instance : IsData Fixture.Types.Datum", source)
        self.assertIn("List (Int)", source)
        self.assertIn("List (ByteString × Int)", source)

    def test_program_and_execution_predicates(self):
        source = self.generated()
        self.assertIn("PlutusV3 single_cbor_hex", source)
        self.assertIn('"Scripts/fixture.example.cbor"', source)
        self.assertIn("Formal.Universal.Properties.rejectedWithin", source)
        self.assertNotIn("theorem ", source)
        self.assertNotIn("sorry", source)

    def test_parameters_preserve_order(self):
        self.blueprint["validators"][0]["parameters"] = [
            {"title": "owner", "schema": {"dataType": "bytes"}},
            {"title": "limit", "schema": {"dataType": "integer"}}
        ]
        source = self.generated()
        self.assertIn("structure Params where", source)
        self.assertLess(source.index("  owner : ByteString", source.index("structure Params")),
                        source.index("  limit : Int", source.index("structure Params")))
        self.assertIn("def args (p : Params)", source)
        self.assertIn("def accepts (fuel : Nat) (p : Params)", source)

    def test_option_and_bool(self):
        tr = BLUEPRINT.Translator({
            "Option<Int>": {"anyOf": [
                {"dataType": "constructor", "index": 0, "fields": [{"dataType": "integer"}]},
                {"dataType": "constructor", "index": 1, "fields": []}
            ]},
            "Bool": {"anyOf": [
                {"dataType": "constructor", "index": 0, "fields": []},
                {"dataType": "constructor", "index": 1, "fields": []}
            ]}
        })
        self.assertEqual(BLUEPRINT.lean_type(tr.ty({"$ref": "#/definitions/Option<Int>"}, "test")),
                         "Option (Int)")
        self.assertEqual(BLUEPRINT.lean_type(tr.ty({"$ref": "#/definitions/Bool"}, "test")),
                         "Bool")

    def test_tuple_type(self):
        tr = BLUEPRINT.Translator({})
        ty = tr.ty({"dataType": "list", "items": [
            {"dataType": "integer"}, {"dataType": "bytes"}
        ]}, "test")
        self.assertIn("Int", BLUEPRINT.lean_type(ty))
        self.assertIn("ByteString", BLUEPRINT.lean_type(ty))
        self.assertIn("×", BLUEPRINT.lean_type(ty))

    def test_reserved_field_is_quoted(self):
        self.blueprint["definitions"]["fixture/types/Datum"]["anyOf"][0]["fields"][0]["title"] = "where"
        self.assertIn("«where» : Int", self.generated())

    def test_unknown_schema_fails(self):
        self.blueprint["definitions"]["fixture/types/Datum"]["anyOf"][0]["fields"][0] = {
            "dataType": "unknown"
        }
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "unknown dataType"):
            self.generated()

    def test_missing_definition_fails(self):
        self.blueprint["validators"][0]["datum"]["schema"] = {"$ref": "#/definitions/missing"}
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "missing definition"):
            self.generated()

    def test_unsupported_version_fails(self):
        self.blueprint["preamble"]["plutusVersion"] = "v2"
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "not supported"):
            self.generated()

    def test_missing_validator_fails(self):
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "no validator"):
            BLUEPRINT.find_entries(self.blueprint, "missing")

    def test_ambiguous_validator_fails(self):
        other = copy.deepcopy(self.blueprint["validators"][0])
        other["title"] = "other.example.spend"
        self.blueprint["validators"].append(other)
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "ambiguous"):
            BLUEPRINT.find_entries(self.blueprint, "example")
        self.assertEqual(len(BLUEPRINT.find_entries(self.blueprint, "fixture.example")), 2)

    def test_mismatched_handler_code_fails(self):
        self.blueprint["validators"][1]["compiledCode"] = "420001"
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "different compiled code"):
            self.generated()

    def test_module_path_validation(self):
        self.assertEqual(BLUEPRINT.module_prefix("Formal/Fixture/Blueprint"),
                         "Formal.Fixture.Blueprint")
        for invalid in ("Other/Fixture", "Formal/lowercase", "../Formal/Fixture"):
            with self.subTest(invalid=invalid), self.assertRaises(BLUEPRINT.ExtractError):
                BLUEPRINT.module_prefix(invalid)

    def test_cli_cbor_is_exact_copy(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.cli(root, "--cbor-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(root) / "Scripts/fixture.example.cbor").read_text(), "4100")
            self.assertEqual(result.stdout.strip(), "Scripts/fixture.example.cbor")

    def test_cli_writes_only_types_and_keeps_other_files(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "Formal/Fixture/Blueprint"
            out.mkdir(parents=True)
            protected = ("Tx.lean", "Checks.lean", "General.lean", "Honest.lean")
            for name in protected:
                (out / name).write_text("-- existing content\n")
            result = self.cli(root, "--out", "Formal/Fixture/Blueprint")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / "Types.lean").read_text(), self.generated())
            for name in protected:
                self.assertEqual((out / name).read_text(), "-- existing content\n")
            self.assertFalse((Path(root) / "Scripts").exists())

    def test_cli_unknown_schema_returns_failure(self):
        self.blueprint["validators"][0]["datum"]["schema"] = {"dataType": "unknown"}
        with tempfile.TemporaryDirectory() as root:
            result = self.cli(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown dataType", result.stderr)

    def test_translation_table_needs_no_blueprint(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), "--translation"],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Schema form", result.stdout)


    def return_source(self):
        lines, info = BLUEPRINT.generate(self.blueprint, "example", "Formal.Fixture.Blueprint.ReturnDatum",
                                         "Scripts", inline_script=True)
        return "\n".join(["import Blaster", "import Formal.Universal.ReturnDatum"] + lines
                          + BLUEPRINT.return_datum_checks(self.blueprint, info)) + "\n"

    def use_matching_hash(self):
        for entry in self.blueprint["validators"]:
            entry["hash"] = hashlib.blake2b(b"\x03" + bytes.fromhex(entry["compiledCode"]), digest_size=28).hexdigest()

    def test_return_datum_full_context_and_output_list(self):
        self.use_matching_hash()
        source = self.return_source()
        self.assertIn("∀ (ctx : ScriptContext), validScriptContext ctx = true →", source)
        self.assertIn("accepts ledgerFuel ctx →", source)
        self.assertIn("ctx.scriptContextTxInfo.txInfoOutputs = true", source)
        self.assertIn("allReturnDatumsValid returnDatumScriptHash returnDatumConforms", source)
        for absent in (".Tx", "firstContinuation", "redirectContinuations", "reindexOutputDatum", "sorry",
                       "import Formal.Fixture.Blueprint.Types", "#import_uplc"):
            self.assertNotIn(absent, source)

    def test_return_datum_hash_is_the_compiled_snapshot_hash(self):
        self.use_matching_hash()
        digest = bytes.fromhex(self.blueprint["validators"][0]["hash"])
        self.assertIn(", ".join(str(n) for n in digest), self.return_source())
        self.blueprint["validators"][1]["hash"] = "00" * 28
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "hash does not match"):
            self.return_source()

    def test_return_datum_rejects_missing_hash(self):
        self.use_matching_hash()
        del self.blueprint["validators"][0]["hash"]
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "hash does not match"):
            self.return_source()

    def test_return_datum_uses_schema_aware_map_decoder(self):
        self.use_matching_hash()
        self.blueprint["validators"][0]["datum"]["schema"] = {
            "dataType": "map", "keys": {"dataType": "bytes"}, "values": {"dataType": "integer"}}
        source = self.return_source()
        self.assertIn("match datum with | Data.Map", source)
        self.assertIn("Option SpendDatum", source)
        self.assertNotIn("IsData.fromData datum : Option SpendDatum", source)

    def test_return_datum_uses_schema_aware_tuple_decoder(self):
        self.use_matching_hash()
        self.blueprint["validators"][0]["datum"]["schema"] = {
            "dataType": "list", "items": [{"dataType": "integer"}, {"dataType": "bytes"}]}
        self.assertIn("match datum with | Data.List [", self.return_source())

    def test_return_datum_refuses_remaining_parameters_on_any_entry(self):
        self.use_matching_hash()
        self.blueprint["validators"][1]["parameters"] = [
            {"title": "owner", "schema": {"dataType": "bytes"}}]
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "remaining blueprint parameters"):
            self.return_source()

    def test_return_datum_refuses_missing_spending_datum(self):
        self.use_matching_hash()
        del self.blueprint["validators"][0]["datum"]
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "declared spending datum"):
            self.return_source()

    def test_return_datum_refuses_recursive_datum(self):
        self.use_matching_hash()
        self.blueprint["definitions"]["fixture/types/Datum"]["anyOf"][0]["fields"].append(
            {"title": "recursive", "$ref": "#/definitions/fixture~1types~1Datum"})
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "recursive datum"):
            self.return_source()

    def test_return_datum_refuses_untranslated_constraints(self):
        self.use_matching_hash()
        self.blueprint["validators"][0]["datum"]["schema"] = {"dataType": "integer", "minimum": 0}
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "datum constraints: minimum"):
            self.return_source()

    def test_return_datum_refuses_ambiguous_constructor_tags(self):
        self.use_matching_hash()
        constructors = self.blueprint["definitions"]["fixture/types/Datum"]["anyOf"]
        constructors.append(dict(copy.deepcopy(constructors[0]), title="OtherDatum"))
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "distinct constructor tags"):
            self.return_source()

    def test_return_datum_refuses_empty_tuple_schema(self):
        self.use_matching_hash()
        self.blueprint["validators"][0]["datum"]["schema"] = {"dataType": "list", "items": []}
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "empty tuple"):
            self.return_source()

    def test_return_datum_refuses_nonstandard_ledger_fields(self):
        self.use_matching_hash()
        self.blueprint["definitions"]["cardano/address/Credential"] = {"anyOf": [
            {"dataType": "constructor", "index": n, "fields": [{"dataType": "integer"}]}
            for n in (0, 1)]}
        self.blueprint["validators"][0]["datum"]["schema"] = {"$ref": "#/definitions/cardano~1address~1Credential"}
        with self.assertRaisesRegex(BLUEPRINT.ExtractError, "ledger decoder"):
            self.return_source()

    def test_return_datum_cli_writes_checks_without_touching_author_files(self):
        self.use_matching_hash()
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "Formal/Fixture/Blueprint"
            out.mkdir(parents=True)
            (out / "Tx.lean").write_text("-- author content\n")
            (out / "Types.lean").write_text("-- existing types\n")
            result = self.cli(root, "--out", "Formal/Fixture/Blueprint", "--check", "returnDatum")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / "Checks.lean").read_text(), self.return_source())
            self.assertEqual((out / "Types.lean").read_text(), "-- existing types\n")
            self.assertEqual((out / "Tx.lean").read_text(), "-- author content\n")
            self.assertEqual({p.name for p in out.iterdir()}, {"Checks.lean", "Types.lean", "Tx.lean"})

    def test_return_datum_cli_needs_no_external_cbor_or_types(self):
        self.use_matching_hash()
        with tempfile.TemporaryDirectory() as root:
            result = self.cli(root, "--out", "Formal/Fixture/Blueprint", "--check", "returnDatum")
            self.assertEqual(result.returncode, 0, result.stderr)
            out = Path(root) / "Formal/Fixture/Blueprint"
            self.assertEqual({p.name for p in out.iterdir()}, {"Checks.lean"})
            self.assertFalse((Path(root) / "Scripts").exists())
            self.assertEqual((out / "Checks.lean").read_text(), self.return_source())

    def test_return_datum_failure_preserves_existing_generated_files(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "Formal/Fixture/Blueprint"
            out.mkdir(parents=True)
            for name in ("Types.lean", "Checks.lean"):
                (out / name).write_text("-- previous output\n")
            result = self.cli(root, "--out", "Formal/Fixture/Blueprint", "--check", "returnDatum")
            self.assertNotEqual(result.returncode, 0)
            for name in ("Types.lean", "Checks.lean"):
                self.assertEqual((out / name).read_text(), "-- previous output\n")


if __name__ == "__main__":
    unittest.main()
