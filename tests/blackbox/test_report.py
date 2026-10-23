"""Black-box tests for the report subcommand (AC-9, AC-10, AC-14)."""

import tempfile
import unittest
from pathlib import Path

from helpers import run


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def schema(self):
        return self.write(
            "schema.json",
            '{"columns":[{"name":"text","type":"string","required":false}]}',
        )

    def test_ac_9_html_escape_in_markdown(self):
        schema = self.schema()
        data = self.write("data.csv", 'text\n"<script>"\n"&"\n""""\n')
        out = self.root / "out.md"
        result = run("report", "--schema", schema, "--out", out, data)
        self.assertEqual(result.returncode, 0, result.stderr)
        markdown = out.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("&amp;", markdown)
        self.assertIn("&quot;", markdown)
        self.assertNotIn("<script>", markdown)

    def test_ac_10_now_is_deterministic(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        out = self.root / "out.md"
        result = run(
            "report",
            "--schema",
            schema,
            "--out",
            out,
            "--now",
            "2026-10-06T12:00:00Z",
            data,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Generated at: `2026-10-06T12:00:00Z`", out.read_text(encoding="utf-8"))

    def test_ac_14_json_with_report_is_usage_error(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        out = self.root / "out.md"
        result = run("report", "--schema", schema, "--out", out, "--json", data)
        self.assertEqual(result.returncode, 1)
        self.assertNotEqual(result.stderr.strip(), "")
        self.assertFalse(out.exists())

    def test_out_dash_writes_to_stdout(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        result = run(
            "report",
            "--schema",
            schema,
            "--out",
            "-",
            "--now",
            "2026-10-06T12:00:00Z",
            data,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Data Quality Report"))
        self.assertIn("Generated at: `2026-10-06T12:00:00Z`", result.stdout)
        self.assertFalse((self.root / "out.md").exists())
        self.assertEqual(
            sorted(entry.name for entry in self.root.iterdir()),
            ["data.csv", "schema.json"],
        )

    def test_no_temporary_files_left_behind(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        out_dir = self.root / "outdir"
        out_dir.mkdir()
        out = out_dir / "report.md"
        result = run("report", "--schema", schema, "--out", out, data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([entry.name for entry in out_dir.iterdir()], ["report.md"])

    def test_unwritable_out_directory_exits_two(self):
        schema = self.schema()
        data = self.write("data.csv", "text\nhello\n")
        out = self.root / "missing-dir" / "report.md"
        result = run("report", "--schema", schema, "--out", out, data)
        self.assertEqual(result.returncode, 2)
        self.assertNotEqual(result.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
