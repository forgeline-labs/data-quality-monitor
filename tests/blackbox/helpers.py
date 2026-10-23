"""Shared helpers for the black-box acceptance tests.

The tests never import the implementation: every invocation goes through the
``./app`` executable in a subprocess, exactly like a real user would.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*args, stdin=None, cwd=None):
    """Run ./app with *args* and return the completed process."""
    return subprocess.run(
        [str(APP), *[str(arg) for arg in args]],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )


def run_json(*args, stdin=None, cwd=None):
    """Run ./app and parse its stdout as a single JSON document."""
    result = run(*args, stdin=stdin, cwd=cwd)
    payload = json.loads(result.stdout)
    return result, payload
