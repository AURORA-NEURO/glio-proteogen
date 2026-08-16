"""Verify deterministic M10-08 release evidence without external authority access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MODULE = "GLIO-PROTEOGEN-M10-08"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES = "3584-3627"
MIN_COVERAGE = 95.0


class ReleaseEvidenceError(ValueError):
    """Raised when an M10-08 release receipt is incomplete or inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleaseEvidenceError(f"{path.name} must contain a JSON object")  # noqa: TRY003
    return value


def verify(directory: Path) -> None:  # noqa: C901
    evaluation = _read(directory / "evaluation.json")
    benchmark = _read(directory / "benchmark.json")
    package = _read(directory / "package.json")
    coverage = _read(directory / "coverage.json")
    for item in (evaluation, benchmark, package):
        if item.get("module") != MODULE:
            raise ReleaseEvidenceError("release evidence module identifiers must match")  # noqa: TRY003
        if item.get("authority_sha256") != AUTHORITY_SHA256:
            raise ReleaseEvidenceError("release evidence authority digest mismatch")  # noqa: TRY003
        if item.get("authority_lines") != AUTHORITY_LINES:
            raise ReleaseEvidenceError("release evidence authority line slice mismatch")  # noqa: TRY003
    if evaluation.get("passed") is not True:
        raise ReleaseEvidenceError("evaluator did not pass")  # noqa: TRY003
    if benchmark.get("passed") is not True:
        raise ReleaseEvidenceError("benchmark did not pass")  # noqa: TRY003
    if benchmark["mean_ns"] > benchmark["mean_budget_ns"]:
        raise ReleaseEvidenceError("benchmark mean exceeded budget")  # noqa: TRY003
    if benchmark["p95_ns"] > benchmark["p95_budget_ns"]:
        raise ReleaseEvidenceError("benchmark p95 exceeded budget")  # noqa: TRY003
    if package.get("passed") is not True or not package.get("artifacts"):
        raise ReleaseEvidenceError("package evidence is incomplete")  # noqa: TRY003
    totals = coverage.get("totals", {})
    if float(totals.get("percent_covered", 0.0)) < MIN_COVERAGE:
        raise ReleaseEvidenceError("branch-enabled coverage is below 95 percent")  # noqa: TRY003
    print("M10-08 release evidence verified")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)


if __name__ == "__main__":
    main()
