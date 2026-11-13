"""Public CLI regressions for exact integer metrics and finite large deviations."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run


class NumericRegressionTests(unittest.TestCase):
    def invoke(self, values, type_name="integer", *args):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(
                json.dumps({"columns": [{"name": "value", "type": type_name}]}),
                encoding="utf-8",
            )
            return run(
                "analyze",
                "--schema",
                schema,
                *args,
                stdin="value\n" + "".join(f"{value}\n" for value in values),
            )

    def test_adjacent_large_integers_remain_distinct_and_exact(self):
        for sign in (1, -1):
            with self.subTest(sign=sign):
                values = sorted(sign * (2**53 + offset) for offset in (0, 1, 2))
                proc = self.invoke(values, "integer", "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                column = json.loads(proc.stdout)["columns"][0]
                self.assertEqual(column["distinct_count"], 3)
                for key, expected in zip(
                    ("min", "q1", "q2", "mean", "q3", "max", "iqr"),
                    (values[0], values[0], values[1], values[1], values[2], values[2], 2),
                ):
                    self.assertEqual(column[key], expected, key)
                self.assertEqual(column["stddev"], 0.816497)
                text = self.invoke([values[1]])
                self.assertIn(f"min: {values[1]}.00", text.stdout)

    def test_even_large_integer_median(self):
        value = 2**53 + 1
        proc = self.invoke([value, value], "integer", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["columns"][0]["q2"], value)

    def test_large_integer_outlier_boundary_stays_exact(self):
        proc = self.invoke(
            [2**53 + offset for offset in range(5)],
            "integer",
            "--json",
            "--outlier-threshold",
            "0",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["columns"][0]["outlier_count"], 1)

    def test_large_finite_population_deviation(self):
        for values, mean, stddev in (
            ([0, 1e155], 5e154, 5e154),
            ([-1e155, 1e155], 0, 1e155),
            ([1e308, 1e308], 1e308, 0),
        ):
            with self.subTest(values=values):
                proc = self.invoke(values, "float", "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                column = json.loads(proc.stdout)["columns"][0]
                for key, expected in (("mean", mean), ("stddev", stddev)):
                    self.assertTrue(math.isfinite(column[key]))
                    self.assertTrue(math.isclose(column[key], expected, rel_tol=1e-12))
                self.assertTrue(math.isfinite(column["q2"]))

    def test_readme_examples_match_cli(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        json_example = next(
            block.split("\n```", 1)[0]
            for block in readme.split("```json\n")[1:]
            if '"command":"analyze"' in block.split("\n```", 1)[0]
        )
        example = json.loads(json_example)
        proc = run(
            "analyze",
            "--schema",
            "tests/fixtures/ac1_schema.json",
            "--baseline",
            "tests/fixtures/ac1_baseline.json",
            "--json",
            "tests/fixtures/ac1.csv",
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), example)
        for command, marker in (
            ("analyze", "```text\nformat: csv"),
            ("report", "```markdown\n# Data Quality Report"),
        ):
            args = [command, "--schema", "tests/fixtures/ac1_schema.json"]
            if command == "report":
                args += [
                    "--baseline",
                    "tests/fixtures/ac1_baseline.json",
                    "--out",
                    "-",
                    "--now",
                    "2026-10-06T12:00:00Z",
                ]
            proc = run(*args, "tests/fixtures/ac1.csv", cwd=ROOT)
            expected = readme.split(marker, 1)[1].split("\n```", 1)[0]
            expected = marker.split("\n", 1)[1] + expected
            self.assertEqual(proc.stdout.strip(), expected.strip())
