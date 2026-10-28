"""Stdlib-only regression tests for the blueprint type/CBOR foundation."""
import copy
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


if __name__ == "__main__":
    unittest.main()
