"""Command-line entry point for data-quality-monitor."""

import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone

from . import JSON_VERSION, VERSION
from .csvdata import InputError, parse_csv, read_text, row_values
from .metrics import analyze_column
from .render import (
    render_analyze_text,
    render_report_markdown,
    render_validate_text,
    to_json,
)
from .schema import SchemaError, is_null, load_schema, validate_cell

COMMANDS = ("validate", "analyze", "report")
BASE_VALUE_FLAGS = {"--schema", "--format"}
COMMON_BOOL_FLAGS = {"--json", "--quiet"}
COMMAND_VALUE_FLAGS = {
    "validate": set(),
    "analyze": {"--baseline", "--outlier-threshold"},
    "report": {"--baseline", "--outlier-threshold", "--out", "--now"},
}
COMMAND_BOOL_FLAGS = {
    "validate": {"--strict"},
    "analyze": set(),
    "report": set(),
}

HELP_TEXT = """Usage: ./app <command> [options] [FILE]

Commands:
  validate   Validate a CSV file against a schema
  analyze    Compute quality metrics for a CSV file
  report     Generate a Markdown data quality report

Options:
  --schema PATH          JSON schema file (required)
  --format FORMAT        Input format (only 'csv' is supported)
  --json                 Emit compact JSON on stdout
  --quiet                Suppress warnings on stderr
  --help                 Show this help and exit
  --version              Show the version and exit

validate options:
  --strict               Exit 3 when any row is invalid

analyze options:
  --baseline PATH        Baseline metrics JSON
  --outlier-threshold K  IQR multiplier (default: 1.5)

report options:
  --baseline PATH        Baseline metrics JSON
  --outlier-threshold K  IQR multiplier (default: 1.5)
  --out PATH             Output Markdown path ('-' for stdout, required)
  --now ISO8601          Override the generation timestamp
"""


class UsageError(Exception):
    """Invalid command-line usage (exit code 1)."""


class Args:
    def __init__(self):
        self.command = None
        self.values = {}
        self.flags = set()
        self.file = None


def _value_flags(command):
    return BASE_VALUE_FLAGS | COMMAND_VALUE_FLAGS[command]


def _bool_flags(command):
    return COMMON_BOOL_FLAGS | COMMAND_BOOL_FLAGS[command]


def parse_args(argv):
    if not argv:
        raise UsageError("missing command")

    command = argv[0]
    if command not in COMMANDS:
        raise UsageError(f"unknown command: {command}")

    args = Args()
    args.command = command
    value_flags = _value_flags(command)
    bool_flags = _bool_flags(command)
    positionals = []

    index = 1
    while index < len(argv):
        token = argv[index]
        if token.startswith("--"):
            if "=" in token:
                name, value = token.split("=", 1)
                if name not in value_flags:
                    raise UsageError(f"unknown flag: {name}")
                args.values[name] = value
            elif token in value_flags:
                if index + 1 >= len(argv):
                    raise UsageError(f"missing value for {token}")
                args.values[token] = argv[index + 1]
                index += 1
            elif token in bool_flags:
                args.flags.add(token)
            else:
                raise UsageError(f"unknown flag: {token}")
        elif token.startswith("-") and token != "-":
            raise UsageError(f"unknown flag: {token}")
        else:
            positionals.append(token)
        index += 1

    if len(positionals) > 1:
        raise UsageError("too many positional arguments")
    args.file = positionals[0] if positionals else None

    if "--json" in args.flags and command == "report":
        raise UsageError("--json is not allowed with report")

    return args


def _validate_options(args):
    if "--schema" not in args.values:
        raise UsageError("--schema is required")

    input_format = args.values.get("--format", "csv")
    if input_format != "csv":
        raise UsageError(f"unsupported format: {input_format}")

    threshold = 1.5
    if "--outlier-threshold" in args.values:
        raw = args.values["--outlier-threshold"]
        try:
            threshold = float(raw)
        except ValueError as exc:
            raise UsageError(f"invalid outlier threshold: {raw}") from exc
        if not math.isfinite(threshold) or threshold < 0:
            raise UsageError(f"invalid outlier threshold: {raw}")
    args.values["--outlier-threshold"] = threshold

    if args.command == "report" and "--out" not in args.values:
        raise UsageError("--out is required for report")


def load_baseline(path):
    """Load a baseline JSON document and index expected metrics by column."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise InputError(f"cannot read baseline '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid baseline JSON '{path}': {exc}") from exc

    if not isinstance(data, dict):
        return {}
    columns = data.get("columns", data)
    if isinstance(columns, list):
        indexed = {}
        for entry in columns:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                indexed[entry["name"]] = entry
        return indexed
    if isinstance(columns, dict):
        return {name: entry for name, entry in columns.items() if isinstance(entry, dict)}
    return {}


def _validate_rows(csv_data, schema):
    """Return per-row error lists and the flat error list."""
    columns = schema["columns"]
    header = csv_data.header
    rows = []
    row_errors = []
    all_errors = []
    for line_number, fields in csv_data.rows:
        values = row_values(header, fields)
        rows.append(values)
        errors = []
        for column in columns:
            for column_name, raw, type_name, message in validate_cell(
                column, values.get(column["name"])
            ):
                error = {
                    "row": line_number,
                    "column": column_name,
                    "value": raw,
                    "expected_type": type_name,
                    "error": message,
                }
                errors.append(error)
                all_errors.append(error)
        row_errors.append(errors)
    return rows, row_errors, all_errors


def _input_block(csv_data, row_errors, source, path):
    valid = sum(1 for errors in row_errors if not errors)
    return {
        "source": source,
        "path": path,
        "format": "csv",
        "lines_total": csv_data.lines_total,
        "lines_valid": valid,
        "lines_invalid": csv_data.lines_total - valid,
    }


def _exit_code(command, input_block, strict):
    invalid = input_block["lines_invalid"]
    if input_block["lines_total"] == 0 or invalid == 0:
        return 0
    if strict or input_block["lines_valid"] == 0:
        return 3
    return 0


def _warn(input_block, args):
    if input_block["lines_invalid"] > 0 and "--quiet" not in args.flags:
        sys.stderr.write(f"warning: {input_block['lines_invalid']} invalid line(s) skipped\n")


def _columns_with_baseline(schema, rows, lines_total, threshold, baseline):
    columns = []
    for column in schema["columns"]:
        entry = baseline.get(column["name"]) if baseline else None
        columns.append(analyze_column(column, rows, lines_total, threshold, entry))
    return columns


def _samples(schema, rows):
    samples = {}
    for column in schema["columns"]:
        name = column["name"]
        values = [values.get(name) for values in rows]
        samples[name] = [raw for raw in values if not is_null(raw)]
    return samples


def _load_schema_or_fail(path):
    try:
        return load_schema(path)
    except SchemaError as exc:
        raise InputError(str(exc)) from exc


def _run(args):
    _validate_options(args)
    schema_path = args.values["--schema"]
    schema = _load_schema_or_fail(schema_path)
    input_format = args.values.get("--format", "csv")

    text, source, echoed_path = read_text(args.file)
    csv_data = parse_csv(text)

    rows, row_errors, all_errors = _validate_rows(csv_data, schema)
    input_block = _input_block(csv_data, row_errors, source, echoed_path)
    input_block["format"] = input_format

    threshold = args.values["--outlier-threshold"]
    baseline = None
    baseline_path = None
    if "--baseline" in args.values:
        baseline_path = args.values["--baseline"]
        baseline = load_baseline(baseline_path)

    if args.command == "validate":
        result = {
            "version": JSON_VERSION,
            "command": "validate",
            "input": input_block,
            "errors": all_errors,
        }
        if "--json" in args.flags:
            sys.stdout.write(to_json(result) + "\n")
        else:
            sys.stdout.write(render_validate_text(result))
        _warn(input_block, args)
        return _exit_code(args.command, input_block, "--strict" in args.flags)

    columns = []
    if csv_data.lines_total > 0:
        columns = _columns_with_baseline(schema, rows, csv_data.lines_total, threshold, baseline)

    if args.command == "analyze":
        result = {
            "version": JSON_VERSION,
            "command": "analyze",
            "input": input_block,
            "outlier_threshold": threshold,
            "columns": columns,
            "baseline_path": baseline_path,
        }
        if "--json" in args.flags:
            sys.stdout.write(to_json(result) + "\n")
        else:
            sys.stdout.write(render_analyze_text(result))
        _warn(input_block, args)
        return _exit_code(args.command, input_block, False)

    # report
    now = args.values.get("--now")
    if now is None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    markdown = render_report_markdown(
        {
            "version": JSON_VERSION,
            "command": "report",
            "input": input_block,
            "outlier_threshold": threshold,
            "columns": columns,
            "baseline_path": baseline_path,
        },
        schema_path,
        now,
        _samples(schema, rows),
        baseline is not None,
    )

    out_path = args.values["--out"]
    if out_path == "-":
        sys.stdout.write(markdown)
    else:
        _write_atomic(out_path, markdown)
    _warn(input_block, args)
    return _exit_code(args.command, input_block, False)


def _write_atomic(path, content):
    directory = os.path.dirname(os.path.abspath(path))
    try:
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".dqm-", suffix=".tmp")
    except OSError as exc:
        raise InputError(f"cannot write output '{path}': {exc}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise InputError(f"cannot write output '{path}': {exc}") from exc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--version" in argv:
        sys.stdout.write(f"data-quality-monitor {VERSION}\n")
        return 0
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(HELP_TEXT)
        return 0

    try:
        args = parse_args(argv)
    except UsageError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    try:
        return _run(args)
    except UsageError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except InputError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001 - last-resort internal error guard
        sys.stderr.write(f"error: unexpected failure: {exc}\n")
        return 4
