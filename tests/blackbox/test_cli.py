"""Black-box tests for CLI behaviour and CSV parsing (AC-8 and general contract)."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import run, run_json


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def schema(self, columns=None):
        columns = columns or [{"name": "text", "type": "string", "required": False}]
        return self.write("schema.json", json.dumps({"columns": columns}))

    def test_ac_8_quoted_csv(self):
        schema = self.schema()
        data = self.write("data.csv", 'text\n"hello, world"\n"quote ""inside"""\n')
        result, payload = run_json("analyze", "--schema", schema, "--json", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_total"], 2)
        self.assertEqual(payload["input"]["lines_valid"], 2)
        self.assertEqual(payload["columns"][0]["distinct_count"], 2)

        report = run(
            "report",
            "--schema",
            schema,
            "--out",
            "-",
            "--now",
            "2026-10-06T12:00:00Z",
            data,
        )
        self.assertIn("hello, world", report.stdout)
        self.assertIn("quote &quot;inside&quot;", report.stdout)

    def test_version_is_exact(self):
        result = run("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "data-quality-monitor 0.1.0\n")

    def test_help_exits_zero(self):
        result = run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertNotEqual((result.stdout + result.stderr).strip(), "")

    def test_unknown_command_exits_one(self):
        result = run("nonsense")
        self.assertEqual(result.returncode, 1)
        self.assertNotEqual(result.stderr.strip(), "")

    def test_unknown_flag_exits_one(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        result = run("validate", "--schema", schema, "--nope", data)
        self.assertEqual(result.returncode, 1)

    def test_unsupported_format_exits_one(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        result = run("validate", "--schema", schema, "--format", "json", data)
        self.assertEqual(result.returncode, 1)

    def test_negative_outlier_threshold_exits_one(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        result = run("analyze", "--schema", schema, "--outlier-threshold", "-1", data)
        self.assertEqual(result.returncode, 1)

    def test_flags_after_file_and_equals_syntax(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        result, payload = run_json("analyze", data, f"--schema={schema}", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_total"], 1)

    def test_stdin_input(self):
        schema = self.schema()
        result, payload = run_json("validate", "--schema", schema, "--json", stdin="text\nhello\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["source"], "stdin")
        self.assertIsNone(payload["input"]["path"])
        self.assertEqual(payload["input"]["lines_valid"], 1)

    def test_relative_path_is_echoed_literally(self):
        schema = self.schema()
        self.write("data.csv", "text\nhello\n")
        result, payload = run_json(
            "validate", "--schema", schema, "--json", "data.csv", cwd=self.root
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["path"], "data.csv")

    def test_blank_lines_are_ignored(self):
        schema = self.schema()
        data = self.write("data.csv", "text\n\n   \nhello\n\n")
        result, payload = run_json("validate", "--schema", schema, "--json", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_total"], 1)

    def test_extra_fields_ignored_and_missing_are_null(self):
        schema = self.schema(
            [
                {"name": "a", "type": "string", "required": False},
                {"name": "b", "type": "string", "required": False},
            ]
        )
        data = self.write("data.csv", "a,b\nonly-a,,\n")
        result, payload = run_json("validate", "--schema", schema, "--json", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_total"], 1)
        self.assertEqual(payload["errors"], [])

    def test_quiet_suppresses_warning(self):
        schema = self.schema([{"name": "age", "type": "integer", "required": True}])
        data = self.write("data.csv", "age\nnope\n")
        noisy = run("validate", "--schema", schema, data)
        quiet = run("validate", "--quiet", "--schema", schema, data)
        self.assertIn("warning:", noisy.stderr)
        self.assertNotIn("warning:", quiet.stderr)

    def test_crlf_input(self):
        schema = self.schema()
        data = self.write("data.csv", "text\r\nhello\r\nworld\r\n")
        result, payload = run_json("validate", "--schema", schema, "--json", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["input"]["lines_total"], 2)
        self.assertEqual(payload["input"]["lines_valid"], 2)


if __name__ == "__main__":
    unittest.main()
