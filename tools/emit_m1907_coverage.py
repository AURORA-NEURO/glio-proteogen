"""Convert scoped coverage.py JSON into the M19-07 evidence schema."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MODULE_ID = "GLIO-PROTEOGEN-M19-07"
FAIL_UNDER = 95.0


class M1907CoverageError(ValueError):
    """Raised when coverage.py output cannot form release evidence."""


def _positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise M1907CoverageError(f"coverage total {field} is invalid")
    return value


def render(raw_path: Path) -> dict[str, Any]:
    document = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("totals"), dict):
        raise M1907CoverageError("coverage.py report must contain totals")
    totals = document["totals"]
    statements = _positive_integer(totals.get("num_statements"), "num_statements")
    covered_statements = _positive_integer(totals.get("covered_lines"), "covered_lines")
    branches = _positive_integer(totals.get("num_branches"), "num_branches")
    covered_branches = _positive_integer(totals.get("covered_branches"), "covered_branches")
    percent = totals.get("percent_covered")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        raise M1907CoverageError("coverage percent is invalid")
    return {
        "module_id": MODULE_ID,
        "branch": True,
        "percent": float(percent),
        "fail_under": FAIL_UNDER,
        "statements": statements,
        "covered_statements": covered_statements,
        "branches": branches,
        "covered_branches": covered_branches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    rendered = json.dumps(render(arguments.raw), indent=2, sort_keys=True) + "\n"
    arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
