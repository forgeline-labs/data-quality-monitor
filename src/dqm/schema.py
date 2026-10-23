"""Schema loading and typed value validation."""

import json
import re
from datetime import date

# Values that are treated as null after CSV parsing (case-insensitive, plus empty).
NULL_TOKENS = {"", "na", "n/a", "null"}

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

TYPE_ERRORS = {
    "integer": "invalid integer format",
    "float": "invalid float format",
    "boolean": "invalid boolean format",
    "date": "invalid date format",
}


class SchemaError(Exception):
    """Raised when the schema file cannot be used."""


def is_null(raw):
    """Return True when a raw cell value represents a null."""
    if raw is None:
        return True
    return raw.strip().lower() in NULL_TOKENS


def load_schema(path):
    """Load a schema JSON document from *path*."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise SchemaError(f"cannot read schema '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"invalid schema JSON '{path}': {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("columns"), list):
        raise SchemaError(f"invalid schema '{path}': expected a 'columns' list")

    columns = []
    for entry in data["columns"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SchemaError(f"invalid schema '{path}': every column needs a name")
        column = dict(entry)
        column.setdefault("type", "string")
        column.setdefault("required", False)
        column.setdefault("nullable", True)
        if column["type"] not in {"string", "integer", "float", "boolean", "date"}:
            raise SchemaError(f"invalid schema '{path}': unsupported type '{column['type']}'")
        if "pattern" in column and column["pattern"] is not None:
            if not isinstance(column["pattern"], str):
                raise SchemaError(
                    f"invalid schema '{path}': pattern for '{column['name']}' must be a string"
                )
            try:
                re.compile(column["pattern"])
            except re.error as exc:
                raise SchemaError(
                    f"invalid schema '{path}': bad pattern for '{column['name']}': {exc}"
                ) from exc
        for bound in ("min", "max"):
            if column.get(bound) is not None and (
                isinstance(column[bound], bool) or not isinstance(column[bound], (int, float))
            ):
                raise SchemaError(
                    f"invalid schema '{path}': '{bound}' for '{column['name']}' must be numeric"
                )
        columns.append(column)
    data["columns"] = columns
    return data


def parse_typed(type_name, raw):
    """Parse *raw* according to *type_name*.

    Returns ``(ok, parsed_value)``.
    """
    if type_name == "string":
        return True, raw
    if type_name == "integer":
        if not INT_RE.match(raw):
            return False, None
        return True, int(raw)
    if type_name == "float":
        if not FLOAT_RE.match(raw):
            return False, None
        return True, float(raw)
    if type_name == "boolean":
        lowered = raw.lower()
        if lowered == "true":
            return True, True
        if lowered == "false":
            return True, False
        return False, None
    if type_name == "date":
        try:
            date.fromisoformat(raw)
        except ValueError:
            return False, None
        return True, raw
    return True, raw


def _number_text(value):
    """Render a schema bound without a trailing ``.0`` when it is integral."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def validate_cell(column, raw):
    """Validate one cell and return a list of ``(column, value, type, message)`` errors."""
    name = column["name"]
    type_name = column["type"]
    required = bool(column.get("required", False))
    nullable = column.get("nullable", True)
    errors = []

    if is_null(raw):
        if required:
            errors.append((name, raw, type_name, "required field is null"))
        elif nullable is False:
            errors.append((name, raw, type_name, "null value not allowed"))
        return errors

    ok, parsed = parse_typed(type_name, raw)
    if not ok:
        errors.append((name, raw, type_name, TYPE_ERRORS.get(type_name, "invalid value")))
        return errors

    pattern = column.get("pattern")
    if pattern is not None and type_name == "string":
        if re.search(pattern, raw) is None:
            errors.append((name, raw, type_name, f"value does not match pattern {pattern}"))

    if type_name in {"integer", "float"}:
        if column.get("min") is not None and parsed < column["min"]:
            errors.append(
                (
                    name,
                    raw,
                    type_name,
                    f"value {_number_text(parsed)} below min {_number_text(column['min'])}",
                )
            )
        if column.get("max") is not None and parsed > column["max"]:
            errors.append(
                (
                    name,
                    raw,
                    type_name,
                    f"value {_number_text(parsed)} exceeds max {_number_text(column['max'])}",
                )
            )
    return errors
