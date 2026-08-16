"""Verify the committed M07-08 release-evidence closure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M07-08"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "2504-2547"
CHECK_COUNT: Final = 7
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


class M0708ReleaseEvidenceError(ValueError):
    """Release evidence is missing or fails its module/authority binding."""


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M0708ReleaseEvidenceError(f"unable to read evidence file: {path.name}") from error  # noqa: TRY003
    if not isinstance(value, dict):
        raise M0708ReleaseEvidenceError(f"evidence file is not an object: {path.name}")  # noqa: TRY003
    return value


def verify_evidence(directory: Path) -> dict[str, object]:
    """Verify evaluation, benchmark, and package receipts as one closure."""

    evaluation = _load(directory / "evaluation.json")
    benchmark = _load(directory / "benchmark.json")
    package = _load(directory / "package.json")
    for label, report in (
        ("evaluation", evaluation),
        ("benchmark", benchmark),
        ("package", package),
    ):
        if report.get("module_id") != MODULE_ID:
            raise M0708ReleaseEvidenceError(f"{label} report has the wrong module")  # noqa: TRY003
        if report.get("passed") is not True:
            raise M0708ReleaseEvidenceError(f"{label} report is not passing")  # noqa: TRY003
    if evaluation.get("authority_sha256") != AUTHORITY_SHA256:
        raise M0708ReleaseEvidenceError("evaluation authority digest does not match")  # noqa: TRY003
    if evaluation.get("authority_lines") != AUTHORITY_LINES:
        raise M0708ReleaseEvidenceError("evaluation authority lines do not match")  # noqa: TRY003
    checks = evaluation.get("checks")
    if not isinstance(checks, list) or len(checks) != CHECK_COUNT:
        raise M0708ReleaseEvidenceError("evaluation check inventory is incomplete")  # noqa: TRY003
    if benchmark.get("mean_budget_ns") != MEAN_BUDGET_NS:
        raise M0708ReleaseEvidenceError("benchmark mean budget changed")  # noqa: TRY003
    if benchmark.get("p95_budget_ns") != P95_BUDGET_NS:
        raise M0708ReleaseEvidenceError("benchmark p95 budget changed")  # noqa: TRY003
    if package.get("artifacts") != ["wheel", "sdist"]:
        raise M0708ReleaseEvidenceError("package artifact inventory is incomplete")  # noqa: TRY003
    return {
        "module_id": MODULE_ID,
        "passed": True,
        "evaluation_checks": len(checks),
        "benchmark_iterations": benchmark.get("iterations"),
        "package_artifacts": package.get("artifacts"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    sys.stdout.write(json.dumps(verify_evidence(arguments.directory), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M0708ReleaseEvidenceError", "main", "verify_evidence"]
