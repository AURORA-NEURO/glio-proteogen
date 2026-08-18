"""Verify the M03-05 replay, evaluator, coverage, and package receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-05"
CONTRACT_VERSION: Final = "1.0.0"
EXPECTED_CASE_COUNT: Final = 57
EXPECTED_ARTIFACT_COUNT: Final = 2
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000
MIN_COVERAGE_PERCENT: Final = 95.0


class M0305ReleaseEvidenceError(ValueError):
    """Raised when a committed M03-05 receipt is missing or contradictory."""


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M0305ReleaseEvidenceError(f"unable to read evidence file: {path.name}") from error  # noqa: TRY003
    if not isinstance(value, dict):
        raise M0305ReleaseEvidenceError(f"evidence file is not an object: {path.name}")  # noqa: TRY003
    return cast("dict[str, object]", value)


def _require_report(label: str, report: Mapping[str, object]) -> None:
    if report.get("module_id") != MODULE_ID:
        raise M0305ReleaseEvidenceError(f"{label} report has the wrong module")  # noqa: TRY003
    if report.get("contract_version") != CONTRACT_VERSION:
        raise M0305ReleaseEvidenceError(f"{label} report has the wrong contract")  # noqa: TRY003
    if report.get("passed") is not True:
        raise M0305ReleaseEvidenceError(f"{label} report is not passing")  # noqa: TRY003


def _artifact_receipts(package: Mapping[str, object]) -> list[dict[str, object]]:
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != EXPECTED_ARTIFACT_COUNT:
        raise M0305ReleaseEvidenceError("package must bind exactly wheel and sdist")  # noqa: TRY003
    receipts: list[dict[str, object]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise M0305ReleaseEvidenceError("package artifact receipt is not an object")  # noqa: TRY003
        receipts.append(cast("dict[str, object]", artifact))
    if {item.get("kind") for item in receipts} != {"wheel", "sdist"}:
        raise M0305ReleaseEvidenceError("package artifact kinds are incomplete")  # noqa: TRY003
    return receipts


def _verify_external_artifact(path: Path, receipt: Mapping[str, object]) -> None:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise M0305ReleaseEvidenceError(f"artifact unavailable: {path.name}") from error  # noqa: TRY003
    if len(payload) != receipt.get("size_bytes"):
        raise M0305ReleaseEvidenceError(f"artifact size mismatch: {path.name}")  # noqa: TRY003
    digest = hashlib.sha256(payload).hexdigest()
    if digest != receipt.get("sha256"):
        raise M0305ReleaseEvidenceError(f"artifact digest mismatch: {path.name}")  # noqa: TRY003
    if receipt.get("kind") == "wheel":
        with zipfile.ZipFile(path) as archive:
            members = len(archive.namelist())
    else:
        with tarfile.open(path) as archive:
            members = len(archive.getnames())
    if members != receipt.get("members"):
        raise M0305ReleaseEvidenceError(f"artifact member count mismatch: {path.name}")  # noqa: TRY003


def verify_release(  # noqa: C901
    directory: Path, artifacts_dir: Path | None = None
) -> dict[str, object]:
    """Verify evaluator, benchmark, coverage, and optional external artifacts."""

    evaluation = _load(directory / "evaluation.json")
    benchmark = _load(directory / "benchmark.json")
    coverage = _load(directory / "coverage.json")
    package = _load(directory / "package.json")
    for label, report in (
        ("evaluation", evaluation),
        ("benchmark", benchmark),
        ("package", package),
    ):
        _require_report(label, report)

    if evaluation.get("declared_case_count") != EXPECTED_CASE_COUNT:
        raise M0305ReleaseEvidenceError("evaluation corpus count changed")  # noqa: TRY003
    if evaluation.get("executed_case_count") != EXPECTED_CASE_COUNT:
        raise M0305ReleaseEvidenceError("evaluation did not execute the complete corpus")  # noqa: TRY003
    replay = evaluation.get("replay_verification")
    if (
        not isinstance(replay, dict)
        or replay.get("library") is not True
        or replay.get("api") is not True
        or replay.get("cli") is not True
    ):
        raise M0305ReleaseEvidenceError("replay verification parity is incomplete")  # noqa: TRY003

    if (
        benchmark.get("mean_budget_ns") != MEAN_BUDGET_NS
        or benchmark.get("p95_budget_ns") != P95_BUDGET_NS
    ):
        raise M0305ReleaseEvidenceError("benchmark budgets changed")  # noqa: TRY003
    if float(cast("float", benchmark.get("mean_ns", float("inf")))) > MEAN_BUDGET_NS:
        raise M0305ReleaseEvidenceError("benchmark mean exceeds budget")  # noqa: TRY003
    if float(cast("float", benchmark.get("p95_ns", float("inf")))) > P95_BUDGET_NS:
        raise M0305ReleaseEvidenceError("benchmark p95 exceeds budget")  # noqa: TRY003

    totals = coverage.get("totals")
    if (
        not isinstance(totals, dict)
        or float(cast("float", totals.get("percent_covered", 0.0))) < MIN_COVERAGE_PERCENT
    ):
        raise M0305ReleaseEvidenceError("coverage is below the release threshold")  # noqa: TRY003

    receipts = _artifact_receipts(package)
    if package.get("reproducible_builds") is not True or package.get("isolated_import") is not True:
        raise M0305ReleaseEvidenceError("package reproducibility/import closure is incomplete")  # noqa: TRY003
    if artifacts_dir is not None:
        for receipt in receipts:
            _verify_external_artifact(artifacts_dir / str(receipt["filename"]), receipt)

    return {
        "module_id": MODULE_ID,
        "contract_version": CONTRACT_VERSION,
        "passed": True,
        "evaluation_cases": EXPECTED_CASE_COUNT,
        "coverage_percent": totals.get("percent_covered"),
        "artifacts": [item.get("kind") for item in receipts],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    arguments = parser.parse_args()
    sys.stdout.write(
        json.dumps(
            verify_release(arguments.directory, arguments.artifacts_dir), indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M0305ReleaseEvidenceError", "main", "verify_release"]
