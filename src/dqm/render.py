"""Text, JSON and Markdown rendering."""

import json

from .metrics import NUMERIC_TYPES, round_half_up


def to_json(payload):
    """Compact single-line JSON (no indentation, no superfluous spaces)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _num(value, places=2):
    if value is None:
        return "N/A"
    rounded = round_half_up(value, places)
    return f"{rounded:.{places}f}"


def _value_repr(value):
    if value is None:
        return "null"
    return f'"{value}"'


def render_validate_text(result):
    data = result["input"]
    lines = [
        f"total_lines: {data['lines_total']}",
        f"valid_lines: {data['lines_valid']}",
        f"invalid_lines: {data['lines_invalid']}",
        "",
    ]
    errors = result["errors"]
    if not errors:
        lines.append("errors: none")
    else:
        lines.append("errors:")
        for error in errors:
            lines.append(
                f"  row {error['row']}, column {error['column']}: {error['error']} "
                f"(value: {_value_repr(error['value'])})"
            )
    return "\n".join(lines) + "\n"


def render_analyze_text(result):
    data = result["input"]
    lines = [
        f"format: {data['format']}",
        f"lines_total: {data['lines_total']}",
        f"lines_valid: {data['lines_valid']}",
        f"lines_invalid: {data['lines_invalid']}",
    ]
    for column in result["columns"]:
        lines.append("")
        lines.append(f"column: {column['name']}")
        lines.append(f"  type: {column['type']}")
        lines.append(f"  count: {column['count']}")
        lines.append(f"  null_rate: {_num(column['null_rate'])}%")
        lines.append(f"  distinct_count: {column['distinct_count']}")
        if column["type"] in NUMERIC_TYPES:
            lines.append(f"  min: {_num(column.get('min'))}")
            lines.append(f"  max: {_num(column.get('max'))}")
            lines.append(f"  mean: {_num(column.get('mean'))}")
            lines.append(f"  stddev: {_num(column.get('stddev'))}")
            lines.append(f"  q1: {_num(column.get('q1'))}")
            lines.append(f"  q2: {_num(column.get('q2'))}")
            lines.append(f"  q3: {_num(column.get('q3'))}")
            lines.append(f"  iqr: {_num(column.get('iqr'))}")
            outlier = column.get("outlier_count")
            lines.append(f"  outlier_count: {'N/A' if outlier is None else outlier}")
    return "\n".join(lines) + "\n"


def md_escape(text):
    """Escape HTML-significant characters for Markdown output."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _sample_values(values):
    """Collect up to five distinct non-null raw sample values for a column."""
    samples = []
    for value in values:
        if value not in samples:
            samples.append(value)
        if len(samples) >= 5:
            break
    return samples


def render_report_markdown(result, schema_path, generated_at, columns_samples, baseline_used):
    data = result["input"]
    source_label = data["path"] if data["path"] is not None else "stdin"
    lines = [
        "# Data Quality Report",
        "",
        f"- Input: `{md_escape(source_label)}`",
        f"- Schema: `{md_escape(schema_path)}`",
        f"- Generated at: `{md_escape(generated_at)}`",
        f"- Lines: `{data['lines_valid']} valid, {data['lines_invalid']} invalid`",
        "",
        "## Validation Summary",
        f"- **Total rows:** {data['lines_total']}",
        f"- **Valid rows:** {data['lines_valid']}",
        f"- **Invalid rows:** {data['lines_invalid']}",
        "",
        "## Column Analysis",
    ]

    for column in result["columns"]:
        lines.append("")
        lines.append(f"### {column['name']} ({column['type']})")
        lines.append(f"- **Count:** {column['count']}")
        lines.append(f"- **Null rate:** {_num(column['null_rate'])}%")
        lines.append(f"- **Distinct values:** {column['distinct_count']}")
        samples = _sample_values(columns_samples.get(column["name"], []))
        if samples:
            escaped = ", ".join(f"`{md_escape(value)}`" for value in samples)
            lines.append(f"- **Sample values:** {escaped}")
        if column["type"] in NUMERIC_TYPES:
            lines.append(
                f"- **Min:** {_num(column.get('min'))}, "
                f"**Max:** {_num(column.get('max'))}, "
                f"**Mean:** {_num(column.get('mean'))}"
            )
            lines.append(
                f"- **Q1:** {_num(column.get('q1'))}, "
                f"**Median:** {_num(column.get('q2'))}, "
                f"**Q3:** {_num(column.get('q3'))}"
            )
            lines.append(f"- **IQR:** {_num(column.get('iqr'))}")
            outlier = column.get("outlier_count")
            lines.append(f"- **Outliers detected:** {'N/A' if outlier is None else outlier}")

    if baseline_used:
        lines.append("")
        lines.append("## Baseline Comparison")
        lines.append("")
        lines.append("| Column | Expected Null Rate | Actual Null Rate | Difference |")
        lines.append("|---|---|---|---|")
        for column in result["columns"]:
            comparison = column.get("baseline_comparison")
            if comparison is None:
                continue
            expected = comparison["expected_null_rate"]
            actual = comparison["actual_null_rate"]
            difference = comparison["diff_null_rate"]
            lines.append(
                f"| {md_escape(column['name'])} "
                f"| {'N/A' if expected is None else _num(expected) + '%'} "
                f"| {'N/A' if actual is None else _num(actual) + '%'} "
                f"| {'N/A' if difference is None else _num(difference) + '%'} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"
