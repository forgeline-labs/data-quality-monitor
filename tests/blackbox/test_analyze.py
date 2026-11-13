"""Black-box tests for the analyze subcommand (AC-2, AC-3, AC-4, AC-13, AC-15)."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import APP, FIXTURES, run_json


def column(payload, name):
    for entry in payload["columns"]:
        if entry["name"] == name:
            return entry
    raise AssertionError(f"column {name!r} missing from {payload['columns']}")


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def schema(self, columns):
        return self.write("schema.json", json.dumps({"columns": columns}))

    def test_ac_2_iqr_outlier_detection(self):
        result, payload = run_json(
            "analyze",
            "--schema",
            FIXTURES / "ac2_schema.json",
            "--outlier-threshold",
            "1.5",
            "--json",
            FIXTURES / "ac2.csv",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value = column(payload, "value")
        self.assertEqual(value["count"], 10)
        self.assertAlmostEqual(value["q1"], 3.0, delta=1e-6)
        self.assertAlmostEqual(value["q3"], 9.0, delta=1e-6)
        self.assertAlmostEqual(value["iqr"], 6.0, delta=1e-6)
        self.assertEqual(value["outlier_count"], 1)

    def test_ac_3_null_rate(self):
        schema = self.schema([{"name": "age", "type": "integer", "required": False}])
        data = self.write("data.csv", "age\n30\n25\n\nNA\n40\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        age = column(payload, "age")
        self.assertEqual(payload["input"]["lines_total"], 4)
        self.assertEqual(age["count"], 3)
        self.assertAlmostEqual(age["null_rate"], 25.0, delta=1e-6)

    def test_ac_3b_null_rate_forty_percent(self):
        schema = self.schema([{"name": "age", "type": "integer", "required": False}])
        data = self.write("data.csv", "age\n30\n25\nNA\nnull\n40\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        age = column(payload, "age")
        self.assertEqual(age["count"], 3)
        self.assertAlmostEqual(age["null_rate"], 40.0, delta=1e-6)

    def test_ac_4_baseline_comparison(self):
        schema = self.schema([{"name": "age", "type": "integer", "required": False}])
        data = self.write("data.csv", "age\n10\n20\n30\n40\n")
        baseline = self.write(
            "baseline.json",
            json.dumps(
                {"columns": {"age": {"expected_null_rate": 25.0, "expected_outlier_count": 2}}}
            ),
        )
        result, payload = run_json(
            "analyze", "--schema", schema, "--baseline", baseline, "--json", data
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        comparison = column(payload, "age")["baseline_comparison"]
        self.assertAlmostEqual(comparison["expected_null_rate"], 25.0, delta=1e-6)
        self.assertAlmostEqual(comparison["actual_null_rate"], 0.0, delta=1e-6)
        self.assertAlmostEqual(comparison["diff_null_rate"], -25.0, delta=1e-6)
        self.assertEqual(comparison["expected_outlier_count"], 2.0)
        self.assertEqual(comparison["actual_outlier_count"], 0)
        self.assertEqual(comparison["diff_outlier_count"], -2.0)
        self.assertEqual(payload["baseline_path"], str(baseline))

    def test_ac_13_schema_column_absent_from_csv(self):
        schema = self.schema(
            [
                {"name": "user_id", "type": "integer", "required": True},
                {"name": "email", "type": "string", "required": False},
            ]
        )
        data = self.write("data.csv", "user_id\n1\n2\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        email = column(payload, "email")
        self.assertEqual(email["count"], 0)
        self.assertAlmostEqual(email["null_rate"], 100.0, delta=1e-6)

    def test_ac_15_distinct_values(self):
        schema = self.schema([{"name": "value", "type": "integer", "required": False}])
        data = self.write("data.csv", "value\n1\n1\n2\n3\n3\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        value = column(payload, "value")
        self.assertEqual(value["count"], 5)
        self.assertEqual(value["distinct_count"], 3)

    def test_iqr_zero_never_marks_outliers(self):
        schema = self.schema([{"name": "value", "type": "integer", "required": False}])
        data = self.write("data.csv", "value\n5\n5\n5\n5\n")
        _, payload = run_json(
            "analyze", "--schema", schema, "--outlier-threshold", "0", "--json", data
        )
        value = column(payload, "value")
        self.assertEqual(value["iqr"], 0.0)
        self.assertEqual(value["outlier_count"], 0)

    def test_all_null_numeric_metrics_are_null(self):
        schema = self.schema([{"name": "value", "type": "float", "required": False}])
        data = self.write("data.csv", "value\nNA\n\nnull\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        value = column(payload, "value")
        self.assertEqual(value["count"], 0)
        for key in ("min", "max", "mean", "stddev", "q1", "q2", "q3", "iqr", "outlier_count"):
            self.assertIsNone(value[key], key)

    def test_columns_ordered_as_schema(self):
        schema = self.schema(
            [
                {"name": "user_id", "type": "integer", "required": True},
                {"name": "age", "type": "integer", "required": False},
            ]
        )
        data = self.write("data.csv", "user_id,age,extra\n1,30,x\n2,25,y\n")
        _, payload = run_json("analyze", "--schema", schema, "--json", data)
        self.assertEqual([entry["name"] for entry in payload["columns"]], ["user_id", "age"])
        self.assertEqual(APP.name, "app")


if __name__ == "__main__":
    unittest.main()
