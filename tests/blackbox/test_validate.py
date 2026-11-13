"""Black-box tests for the validate subcommand (AC-1, AC-5, AC-6, AC-7, AC-11, AC-12)."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, run, run_json


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_ac_1_validate_json_simple(self):
        result, payload = run_json(
            "validate",
            "--schema",
            FIXTURES / "ac1_schema.json",
            "--json",
            FIXTURES / "ac1.csv",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["version"], "0.1")
        self.assertEqual(payload["command"], "validate")
        self.assertEqual(payload["input"]["source"], "file")
        self.assertEqual(payload["input"]["format"], "csv")
        self.assertEqual(payload["input"]["lines_total"], 3)
        self.assertEqual(payload["input"]["lines_valid"], 3)
        self.assertEqual(payload["input"]["lines_invalid"], 0)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["input"]["path"], str(FIXTURES / "ac1.csv"))

    def test_ac_5_invalid_lines_do_not_crash(self):
        schema = self.write(
            "schema.json",
            json.dumps(
                {
                    "columns": [
                        {
                            "name": "status",
                            "type": "integer",
                            "required": True,
                            "nullable": False,
                            "min": 0,
                            "max": 10,
                        },
                        {"name": "name", "type": "string", "required": True, "nullable": False},
                    ]
                }
            ),
        )
        data = self.write(
            "data.csv",
            "status,name\n1,ok\n5,fine\n9,good\n99,out-of-range\noops,bad\n",
        )
        result, payload = run_json("validate", "--schema", schema, "--json", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_valid"], 3)
        self.assertEqual(payload["input"]["lines_invalid"], 2)
        self.assertEqual(len(payload["errors"]), 2)
        columns = {error["column"] for error in payload["errors"]}
        self.assertEqual(columns, {"status"})
        rows = {error["row"] for error in payload["errors"]}
        self.assertEqual(rows, {5, 6})
        self.assertIn("warning: 2 invalid line(s) skipped", result.stderr)

    def test_ac_6_strict_exits_three(self):
        schema = self.write(
            "schema.json",
            json.dumps({"columns": [{"name": "age", "type": "integer", "required": True}]}),
        )
        data = self.write("data.csv", "age\n10\nnot-a-number\n")
        result = run("validate", "--strict", "--schema", schema, data)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("invalid_lines: 1", result.stdout)

    def test_ac_7_empty_file(self):
        schema = self.write(
            "schema.json",
            json.dumps({"columns": [{"name": "age", "type": "integer"}]}),
        )
        result, payload = run_json("validate", "--schema", schema, "--json", stdin="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["source"], "stdin")
        self.assertIsNone(payload["input"]["path"])
        self.assertEqual(payload["input"]["lines_total"], 0)
        self.assertEqual(payload["input"]["lines_valid"], 0)
        self.assertEqual(payload["input"]["lines_invalid"], 0)
        self.assertEqual(payload["errors"], [])

        _, analysis = run_json("analyze", "--schema", schema, "--json", stdin="")
        self.assertEqual(analysis["columns"], [])

    def test_ac_11_schema_is_required(self):
        data = self.write("data.csv", "age\n1\n")
        result = run("validate", data)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr.strip(), "")

    def test_ac_12_schema_not_found(self):
        data = self.write("data.csv", "age\n1\n")
        result = run("validate", "--schema", "/not/found.json", data)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
