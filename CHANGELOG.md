# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-06

### Added

- `validate` subcommand: validates a CSV file against a JSON schema and reports
  per-cell errors with row numbers.
- `analyze` subcommand: per-column quality metrics (null rate, distinct count,
  min/max/mean/stddev, nearest-rank-style quartiles and IQR outlier detection).
- `report` subcommand: deterministic Markdown report with validation summary,
  column analysis and optional baseline comparison.
- Schema support for `string`, `integer`, `float`, `boolean` and ISO-8601 `date`
  columns, including `required`, `nullable`, `pattern`, `min` and `max`.
- Streaming-friendly CSV parsing from a file or stdin, tolerant of malformed
  rows, quoted fields, embedded newlines, CRLF and blank lines.
- Compact JSON output mode (`--json`), text output mode, `--quiet`,
  `--outlier-threshold`, `--baseline`, `--out -` and `--now`.
- Black-box acceptance test suite in `tests/blackbox/` driving `./app` through
  subprocesses, plus a `make smoke` check.
- GitHub Actions CI on Linux and macOS.

[0.1.0]: https://github.com/forgeline-labs/data-quality-monitor/releases/tag/v0.1.0
