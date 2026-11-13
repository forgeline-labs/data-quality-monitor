"""Quality metrics: null rates, distribution statistics and IQR outliers."""

import math
from decimal import ROUND_HALF_UP, Decimal

from .schema import is_null, parse_typed

NUMERIC_TYPES = {"integer", "float"}
NUMERIC_KEYS = (
    "min",
    "max",
    "mean",
    "stddev",
    "q1",
    "q2",
    "q3",
    "iqr",
    "outlier_count",
)


def round_half_up(value, places=6):
    """Round *value* half-up to *places* decimals (serialisation helper)."""
    if value is None:
        return None
    quant = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def percentile(sorted_values, fraction):
    """Nearest-rank percentile; clamp ranks to the observed range for small n.

    The median remains the ordinary midpoint for an even-sized sample.
    """
    count = len(sorted_values)
    if count == 0:
        return None
    if fraction == 0.5:
        middle = count // 2
        if count % 2:
            return float(sorted_values[middle])
        return float((sorted_values[middle - 1] + sorted_values[middle]) / 2)
    rank = max(1, min(count, math.ceil(fraction * (count + 1))))
    return float(sorted_values[rank - 1])


def _expected_number(entry, key):
    for candidate in (f"expected_{key}", key):
        if candidate in entry and entry[candidate] is not None:
            value = entry[candidate]
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return value
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _difference(actual, expected):
    difference = actual - expected
    if isinstance(difference, int):
        return difference
    return round_half_up(difference)


def baseline_comparison(column_result, entry):
    """Build the ``baseline_comparison`` object for one column."""
    expected_null = _expected_number(entry, "null_rate")
    actual_null = column_result.get("null_rate")
    expected_outliers = _expected_number(entry, "outlier_count")
    actual_outliers = column_result.get("outlier_count")

    diff_null = None
    if expected_null is not None and actual_null is not None:
        diff_null = _difference(actual_null, expected_null)
    diff_outliers = None
    if expected_outliers is not None and actual_outliers is not None:
        diff_outliers = _difference(actual_outliers, expected_outliers)

    return {
        "expected_null_rate": round_half_up(expected_null),
        "actual_null_rate": actual_null,
        "diff_null_rate": diff_null,
        "expected_outlier_count": expected_outliers,
        "actual_outlier_count": actual_outliers,
        "diff_outlier_count": diff_outliers,
    }


def analyze_column(column, rows, lines_total, outlier_threshold, baseline_entry=None):
    """Compute every metric for one schema column."""
    name = column["name"]
    type_name = column["type"]
    raw_values = [values.get(name) for values in rows]

    null_count = sum(1 for raw in raw_values if is_null(raw))
    non_null = [raw for raw in raw_values if not is_null(raw)]

    numeric_values = []
    canonical = []
    for raw in non_null:
        ok, parsed = parse_typed(type_name, raw)
        if type_name in NUMERIC_TYPES and ok:
            numeric_values.append(float(parsed))
            canonical.append(float(parsed))
        else:
            canonical.append(raw)

    result = {
        "name": name,
        "type": type_name,
        "count": len(non_null),
        "null_rate": round_half_up(null_count / lines_total * 100.0 if lines_total else 0.0),
        "distinct_count": len(set(canonical)),
    }

    if type_name in NUMERIC_TYPES:
        if numeric_values:
            ordered = sorted(numeric_values)
            q1 = percentile(ordered, 0.25)
            q2 = percentile(ordered, 0.5)
            q3 = percentile(ordered, 0.75)
            iqr = q3 - q1
            if iqr == 0:
                outlier_count = 0
            else:
                lower = q1 - outlier_threshold * iqr
                upper = q3 + outlier_threshold * iqr
                outlier_count = sum(1 for value in ordered if value < lower or value > upper)
            mean = sum(ordered) / len(ordered)
            variance = sum((value - mean) ** 2 for value in ordered) / len(ordered)
            result.update(
                {
                    "min": round_half_up(ordered[0]),
                    "max": round_half_up(ordered[-1]),
                    "mean": round_half_up(mean),
                    "stddev": round_half_up(math.sqrt(variance)),
                    "q1": round_half_up(q1),
                    "q2": round_half_up(q2),
                    "q3": round_half_up(q3),
                    "iqr": round_half_up(iqr),
                    "outlier_count": outlier_count,
                }
            )
        else:
            for key in NUMERIC_KEYS:
                result[key] = None

    if baseline_entry is not None:
        result["baseline_comparison"] = baseline_comparison(result, baseline_entry)
    else:
        result["baseline_comparison"] = None
    return result
