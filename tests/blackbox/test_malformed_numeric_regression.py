"""Malformed quoting is invalid; finite scientific notation remains usable."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import run_json


class MalformedAndNumericTests(unittest.TestCase):
    def test_unclosed_quotes_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(json.dumps({"columns": [{"name": "x", "type": "string"}]}))
            cases = [
                ('x\n"broken\nsecond\nthird\n', 3, 1),
                ('x\ngood\n"unfinished', 0, 2),
                ('x\n"quoted"garbage\n', 3, 1),
            ]
            for csv, exit_code, total in cases:
                with self.subTest(csv=csv):
                    result, payload = run_json("validate", "--schema", schema, "--json", stdin=csv)
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    self.assertEqual(payload["input"]["lines_total"], total)
                    self.assertEqual(payload["input"]["lines_invalid"], 1)
                    self.assertIn("malformed CSV", payload["errors"][0]["error"])
                    self.assertIn("invalid", result.stderr)

    def test_malformed_header_is_not_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text('{"columns":[{"name":"x","type":"string"}]}')
            result, payload = run_json(
                "validate", "--schema", schema, "--json", stdin='"x\nvalue\n'
            )
            self.assertEqual(result.returncode, 3)
            self.assertEqual(payload["input"]["lines_invalid"], 1)
            self.assertTrue(payload["errors"])

    def test_large_finite_float_is_serializable(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text('{"columns":[{"name":"x","type":"float"}]}')
            for value in ("1e23", "-1e23", "1e100"):
                with self.subTest(value=value):
                    result, payload = run_json(
                        "analyze", "--schema", schema, "--json", stdin="x\n" + value + "\n"
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(payload["columns"][0]["mean"], float(value))
