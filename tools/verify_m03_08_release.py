"""Verify the M03-08 evaluator, replay, coverage, and package receipts."""

# This standalone receipt verifier intentionally reports precise contextual errors.
# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_ID: Final = "GLIO-PROTEOGEN-M03-08"
CONTRACT_VERSION: Final = "1.0.0"
EXPECTED_CASE_COUNT: Final = 38
EXPECTED_ARCHIVE_MEMBER_COUNT: Final = 10
EXPECTED_SOFTWARE_VERSION_COUNT: Final = 64
EXPECTED_REFERENCE_VERSION_COUNT: Final = 64
EXPECTED_PACKAGE_ARTIFACT_COUNT: Final = 2
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000
MIN_COVERAGE_PERCENT: Final = 95.0
SOURCE_DATE_EPOCH: Final = 315532800
EXPECTED_EVALUATOR_CHECK_NAMES: Final = frozenset(
    {
        "corpus.exact_eight_groups_thirty_eight_cases",
        "scenario.canonical_release",
        "scenario.semantic_reorder_replay",
        "scenario.m03_01_quarantined",
        "scenario.m03_02_unreleasable",
        "scenario.m03_03_unreleasable",
        "scenario.m03_04_quarantined",
        "scenario.m03_05_quarantined",
        "scenario.m03_06_quarantined",
        "scenario.m03_07_abstained",
        "scenario.identity_lineage_substitution",
        "scenario.predecessor_digest_substitution",
        "scenario.harmonization_support_substitution",
        "scenario.artifact_byte_digest_mismatch",
        "scenario.artifact_declared_digest_mismatch",
        "scenario.artifact_size_mismatch",
        "scenario.missing_artifact_member",
        "scenario.undeclared_artifact_member",
        "scenario.duplicate_canonical_member",
        "scenario.unsafe_member_path",
        "scenario.archive_member_alias",
        "scenario.verified_statement_releases",
        "scenario.statement_digest_mismatch_quarantines",
        "scenario.unsupported_signature_algorithm_rejected",
        "scenario.verifier_unavailable_quarantines",
        "scenario.verifier_rejected_quarantines",
        "scenario.malformed_signature_value_rejected",
        "scenario.coerced_integer_rejected",
        "scenario.coerced_boolean_rejected",
        "scenario.unknown_field_rejected",
        "scenario.invalid_enumeration_rejected",
        "scenario.stale_derived_digest_rejected",
        "scenario.semantic_duplicate_rejected",
        "scenario.recursive_output_boundary",
        "scenario.consent_denied_before_hostile_chain",
        "scenario.consent_denied_before_hostile_artifacts",
        "scenario.typed_blocked_recovery",
        "scenario.maximum_accepted_shape",
        "scenario.first_excess_rejected_before_archive",
        "coverage.exact_declared_executable_case_set",
    }
)


class M0308ReleaseEvidenceError(ValueError):
    """Raised when a committed M03-08 receipt is missing or contradictory."""


def _duplicate_key_error(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise M0308ReleaseEvidenceError(f"duplicate evidence key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise M0308ReleaseEvidenceError(f"non-finite evidence number: {value}")


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_key_error,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise M0308ReleaseEvidenceError(f"unable to read evidence file: {path.name}") from error
    if not isinstance(value, dict):
        raise M0308ReleaseEvidenceError(f"evidence file is not an object: {path.name}")
    return cast("dict[str, object]", value)


def _require_report(label: str, report: Mapping[str, object]) -> None:
    if report.get("module_id") != MODULE_ID:
        raise M0308ReleaseEvidenceError(f"{label} report has the wrong module")
    if report.get("contract_version") != CONTRACT_VERSION:
        raise M0308ReleaseEvidenceError(f"{label} report has the wrong contract")
    if report.get("passed") is not True and report.get("status") != "PASS":
        raise M0308ReleaseEvidenceError(f"{label} report is not passing")


def _require_exact_evaluator(evaluation: Mapping[str, object]) -> None:
    if (
        evaluation.get("declared_case_count") != EXPECTED_CASE_COUNT
        or evaluation.get("executed_case_count") != EXPECTED_CASE_COUNT
        or evaluation.get("passed_case_count") != EXPECTED_CASE_COUNT
    ):
        raise M0308ReleaseEvidenceError("evaluator corpus count changed")
    for field in (
        "missing_case_ids",
        "extra_case_ids",
        "duplicate_declared_case_ids",
        "duplicate_executed_case_ids",
    ):
        if evaluation.get(field) != []:
            raise M0308ReleaseEvidenceError(f"evaluator {field} is not empty")
    checks = evaluation.get("checks")
    if not isinstance(checks, list) or len(checks) != EXPECTED_CASE_COUNT + 2:
        raise M0308ReleaseEvidenceError("evaluator check inventory changed")
    names = [item.get("name") for item in checks if isinstance(item, dict)]
    if (
        len(names) != len(checks)
        or any(not isinstance(name, str) for name in names)
        or len(set(names)) != len(names)
        or set(names) != EXPECTED_EVALUATOR_CHECK_NAMES
    ):
        raise M0308ReleaseEvidenceError("evaluator check names do not match the locked corpus")
    if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
        raise M0308ReleaseEvidenceError("evaluator contains a failing or malformed check")


def _require_benchmark(benchmark: Mapping[str, object]) -> None:
    if (
        benchmark.get("mean_budget_ns") != MEAN_BUDGET_NS
        or benchmark.get("p95_budget_ns") != P95_BUDGET_NS
        or benchmark.get("software_version_count") != EXPECTED_SOFTWARE_VERSION_COUNT
        or benchmark.get("reference_version_count") != EXPECTED_REFERENCE_VERSION_COUNT
        or benchmark.get("archive_member_count") != EXPECTED_ARCHIVE_MEMBER_COUNT
        or benchmark.get("workload") != "public_build_exact_64_software_64_reference_shape"
    ):
        raise M0308ReleaseEvidenceError("benchmark workload or budget changed")
    if float(cast("float", benchmark.get("mean_ns", float("inf")))) > MEAN_BUDGET_NS:
        raise M0308ReleaseEvidenceError("benchmark mean exceeds budget")
    if float(cast("float", benchmark.get("p95_ns", float("inf")))) > P95_BUDGET_NS:
        raise M0308ReleaseEvidenceError("benchmark p95 exceeds budget")


def _artifact_receipts(package: Mapping[str, object]) -> list[dict[str, object]]:
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != EXPECTED_PACKAGE_ARTIFACT_COUNT:
        raise M0308ReleaseEvidenceError("package must bind exactly wheel and sdist")
    receipts: list[dict[str, object]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise M0308ReleaseEvidenceError("package artifact receipt is not an object")
        receipts.append(cast("dict[str, object]", artifact))
    if {item.get("kind") for item in receipts} != {"wheel", "sdist"}:
        raise M0308ReleaseEvidenceError("package artifact kinds are incomplete")
    return receipts


def _verify_external_artifact(path: Path, receipt: Mapping[str, object]) -> None:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise M0308ReleaseEvidenceError(f"artifact unavailable: {path.name}") from error
    if len(payload) != receipt.get("size_bytes"):
        raise M0308ReleaseEvidenceError(f"artifact size mismatch: {path.name}")
    if hashlib.sha256(payload).hexdigest() != receipt.get("sha256"):
        raise M0308ReleaseEvidenceError(f"artifact digest mismatch: {path.name}")
    try:
        if receipt.get("kind") == "wheel":
            with zipfile.ZipFile(path) as archive:
                members = len(archive.namelist())
        else:
            with tarfile.open(path) as archive:
                members = len(archive.getnames())
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise M0308ReleaseEvidenceError(f"artifact archive is unreadable: {path.name}") from error
    if members != receipt.get("members"):
        raise M0308ReleaseEvidenceError(f"artifact member count mismatch: {path.name}")


def verify_release(directory: Path, artifacts_dir: Path | None = None) -> dict[str, object]:
    """Verify M03-08 reports and optionally bind them to external build bytes."""

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
    _require_exact_evaluator(evaluation)
    _require_benchmark(benchmark)
    totals = coverage.get("totals")
    if not isinstance(totals, dict):
        raise M0308ReleaseEvidenceError("coverage totals are missing")
    coverage_percent = float(cast("float", totals.get("percent_covered", 0.0)))
    if coverage_percent < MIN_COVERAGE_PERCENT:
        raise M0308ReleaseEvidenceError("coverage is below the release threshold")
    if package.get("source_date_epoch") != SOURCE_DATE_EPOCH:
        raise M0308ReleaseEvidenceError("reproducible-build epoch changed")
    if package.get("reproducible_builds") is not True or package.get("isolated_import") is not True:
        raise M0308ReleaseEvidenceError("package reproducibility/import closure is incomplete")
    receipts = _artifact_receipts(package)
    if artifacts_dir is not None:
        for receipt in receipts:
            _verify_external_artifact(artifacts_dir / str(receipt["filename"]), receipt)
    return {
        "module_id": MODULE_ID,
        "contract_version": CONTRACT_VERSION,
        "passed": True,
        "evaluation_cases": EXPECTED_CASE_COUNT,
        "coverage_percent": coverage_percent,
        "artifacts": [item.get("kind") for item in receipts],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    arguments = parser.parse_args()
    try:
        report = verify_release(arguments.directory, arguments.artifacts_dir)
    except M0308ReleaseEvidenceError as error:
        sys.stderr.write(f"M03-08 release evidence failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M0308ReleaseEvidenceError", "main", "verify_release"]
