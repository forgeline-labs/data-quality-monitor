"""Rank quartiles select observed values; the median averages central values."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import run_json


class RankQuartileTests(unittest.TestCase):
    def test_small_and_uneven_samples(self):
        cases = [
            ([8], (8, 8, 8)),
            ([2, 14], (2, 8, 14)),
            ([0, 4, 12, 20], (4, 8, 20)),
            ([2, 7, 9, 11, 30, 40], (7, 10, 40)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(json.dumps({"columns": [{"name": "reading", "type": "integer"}]}))
            for values, expected in cases:
                with self.subTest(values=values):
                    csv = "reading\n" + "".join(f"{value}\n" for value in values)
                    result, payload = run_json("analyze", "--schema", schema, "--json", stdin=csv)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    column = payload["columns"][0]
                    self.assertEqual(tuple(column[key] for key in ("q1", "q2", "q3")), expected)
