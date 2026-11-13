"""CSV reading and parsing that keeps line numbers and never raises on bad rows."""

import sys


class InputError(Exception):
    """Raised when an input file cannot be read."""


def read_text(path):
    """Read the whole input.

    Returns ``(text, source, echoed_path)`` where *source* is ``file`` or ``stdin``
    and *echoed_path* is the literal FILE argument (``None`` for stdin).
    """
    if path is None or path == "-":
        return sys.stdin.read(), "stdin", None
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as handle:
            text = handle.read()
    except OSError as exc:
        raise InputError(f"cannot read input '{path}': {exc}") from exc
    return text, "file", path


def split_records(text):
    """Split CSV text into logical records.

    Returns a list of ``(line_number, record_text)``. Quoted fields may contain
    newlines; those physical lines are still counted for row numbering.
    """
    records = []
    buffer = []
    in_quotes = False
    line_number = 1
    start_line = 1

    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            buffer.append(char)
        elif char == "\n" and not in_quotes:
            record = "".join(buffer)
            if record.endswith("\r"):
                record = record[:-1]
            records.append((start_line, record))
            buffer = []
            line_number += 1
            start_line = line_number
        else:
            if char == "\n":
                line_number += 1
            buffer.append(char)

    if buffer:
        record = "".join(buffer)
        if record.endswith("\r"):
            record = record[:-1]
        records.append((start_line, record))
    return records


class CsvParseError(ValueError):
    """A logical record has malformed quoting."""


def parse_fields(record):
    """Parse one CSV record into a list of unquoted/trimmed field strings."""
    fields = []
    index = 0
    length = len(record)
    while True:
        if index < length and record[index] == '"':
            index += 1
            buffer = []
            closed = False
            while index < length:
                if record[index] == '"':
                    if index + 1 < length and record[index + 1] == '"':
                        buffer.append('"')
                        index += 2
                    else:
                        index += 1
                        closed = True
                        break
                else:
                    buffer.append(record[index])
                    index += 1
            if not closed:
                raise CsvParseError("unterminated quoted field")
            while index < length and record[index].isspace():
                index += 1
            if index < length and record[index] != ",":
                raise CsvParseError("unexpected text after closing quote")
            fields.append("".join(buffer))
        else:
            start = index
            while index < length and record[index] != ",":
                index += 1
            raw = record[start:index]
            if '"' in raw:
                raise CsvParseError("quote inside an unquoted field")
            fields.append(raw.strip())

        if index < length and record[index] == ",":
            index += 1
            if index == length:
                fields.append("")
                break
            continue
        break
    return fields


class CsvData:
    """Parsed CSV: header names and data rows with their original line numbers."""

    def __init__(self, header, rows, errors=None):
        self.header = header
        self.rows = rows
        self.errors = errors or {}

    @property
    def lines_total(self):
        return len(self.rows)


def parse_csv(text):
    """Parse CSV text into a :class:`CsvData` instance."""
    if text.startswith("﻿"):
        text = text[1:]

    records = [(line, content) for line, content in split_records(text) if content.strip()]
    if not records:
        return CsvData(None, [])

    errors = {}
    rows = []
    try:
        header = [name.strip() for name in parse_fields(records[0][1])]
    except CsvParseError as exc:
        header = None
        line_number = records[0][0]
        rows.append((line_number, None))
        errors[line_number] = str(exc)
    for line_number, content in records[1:]:
        try:
            if header is None:
                raise CsvParseError("malformed header")
            rows.append((line_number, parse_fields(content)))
        except CsvParseError as exc:
            rows.append((line_number, None))
            errors[line_number] = str(exc)
    return CsvData(header, rows, errors)


def row_values(header, fields):
    """Map header names to raw cell values for a row.

    Extra cells are ignored; missing cells (and columns absent from the header)
    map to ``None``.
    """
    values = {}
    if header is None:
        return values
    for index, name in enumerate(header):
        values[name] = fields[index] if index < len(fields) else None
    return values
