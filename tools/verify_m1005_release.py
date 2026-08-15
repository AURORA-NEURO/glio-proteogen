"""Verify the M10-05 locked evidence bundle without executing scientific code."""

# The verifier deliberately raises one domain error for each failed gate.
# ruff: noqa: TRY003, C901, PLR0912

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M10-05"
AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "3452-3495"
EXPECTED_CHECKS: Final = 8
EXPECTED_SCENARIOS: Final = 8
EXPECTED_SCHEMA_COUNT: Final = 7
DIGEST_HEX_LENGTH: Final = 64


class M1005ReleaseEvidenceError(ValueError):
    """Raised when a release evidence artifact is incomplete or contradictory."""


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise M1005ReleaseEvidenceError(f"unable to read {path.name}") from error
    if not isinstance(value, dict):
        raise M1005ReleaseEvidenceError(f"{path.name} must contain an object")
    return value


def _int_field(value: object, name: str) -> int:
    if type(value) is not int:
        raise M1005ReleaseEvidenceError(f"{name} is not an integer")
    return value


def _positive_int_field(value: object, name: str) -> int:
    result = _int_field(value, name)
    if result <= 0:
        raise M1005ReleaseEvidenceError(f"{name} must be positive")
    return result


def verify_evidence(directory: Path) -> dict[str, object]:
    evaluation = _read(directory / "evaluation.json")
    benchmark = _read(directory / "benchmark.json")
    package_path = directory / "package.json"
    if evaluation.get("module_id") != MODULE_ID:
        raise M1005ReleaseEvidenceError("evaluation module identity does not match")
    if evaluation.get("authority_lines") != AUTHORITY_LINES:
        raise M1005ReleaseEvidenceError("evaluation authority lines do not match")
    if evaluation.get("authority_sha256") != AUTHORITY_SHA256:
        raise M1005ReleaseEvidenceError("evaluation authority digest does not match")
    if evaluation.get("passed") is not True:
        raise M1005ReleaseEvidenceError("evaluation did not pass")
    if evaluation.get("check_count") != EXPECTED_CHECKS:
        raise M1005ReleaseEvidenceError("evaluation check inventory is incomplete")
    checks = evaluation.get("checks")
    if not isinstance(checks, list) or len(checks) != EXPECTED_CHECKS:
        raise M1005ReleaseEvidenceError("evaluation checks are missing")
    if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
        raise M1005ReleaseEvidenceError("one or more evaluator checks failed")
    if benchmark.get("module_id") != MODULE_ID:
        raise M1005ReleaseEvidenceError("benchmark module identity does not match")
    if benchmark.get("passed") is not True or benchmark.get("deterministic") is not True:
        raise M1005ReleaseEvidenceError("benchmark did not pass determinism or budget gates")
    mean_ns = _int_field(benchmark.get("mean_ns"), "mean_ns")
    p95_ns = _int_field(benchmark.get("p95_ns"), "p95_ns")
    mean_budget_ns = _int_field(benchmark.get("mean_budget_ns"), "mean_budget_ns")
    p95_budget_ns = _int_field(benchmark.get("p95_budget_ns"), "p95_budget_ns")
    if mean_ns > mean_budget_ns or p95_ns > p95_budget_ns:
        raise M1005ReleaseEvidenceError("benchmark budgets changed or were exceeded")
    package_present = package_path.exists()
    if package_present:
        package = _read(package_path)
        if package.get("module_id") != MODULE_ID:
            raise M1005ReleaseEvidenceError("package module identity does not match")
        if (
            package.get("schema_count") != EXPECTED_SCHEMA_COUNT
            or package.get("isolated_import") is not True
        ):
            raise M1005ReleaseEvidenceError("package schema/import evidence is incomplete")
        for field in ("wheel_bytes", "sdist_bytes", "wheel_members", "sdist_members"):
            _positive_int_field(package.get(field), f"package {field}")
        for field in ("wheel_sha256", "sdist_sha256"):
            value = package.get(field)
            if not isinstance(value, str) or len(value) != DIGEST_HEX_LENGTH:
                raise M1005ReleaseEvidenceError(f"package {field} is invalid")
    return {
        "module_id": MODULE_ID,
        "evaluation_checks": EXPECTED_CHECKS,
        "scenario_count": EXPECTED_SCENARIOS,
        "benchmark_passed": True,
        "package_present": package_present,
        "verified": True,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    directory = Path(arguments[0]) if arguments else Path("release-evidence/m10_05")
    try:
        report = verify_evidence(directory)
    except M1005ReleaseEvidenceError as error:
        sys.stderr.write(f"M10-05 release evidence failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M1005ReleaseEvidenceError", "main", "verify_evidence"]
