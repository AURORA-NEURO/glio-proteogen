"""Verify research-only pilot evidence and optional package artifacts."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODULE = "RESEARCH-PUBLIC-PROTEOMICS-PILOT"
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 72 * 1024 * 1024
EXPECTED_ARTIFACTS = 2
SHA256_LENGTH = 64
SOURCE_DATE_EPOCH = 315532800


class ResearchPilotEvidenceError(ValueError):
    """Raised when the pilot evidence receipt is incomplete or unsafe."""


@dataclass(frozen=True)
class _ArtifactReceipt:
    kind: str
    filename: str
    size: int
    digest: str
    members: int


def _read(evidence_root: Path, name: str) -> dict[str, Any]:
    path = evidence_root / name
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ResearchPilotEvidenceError("evidence file exceeds the bounded size")
        with path.open("rb") as stream:
            payload = stream.read(MAX_EVIDENCE_BYTES + 1)
        if len(payload) > MAX_EVIDENCE_BYTES:
            raise ResearchPilotEvidenceError("evidence file exceeds the bounded size")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResearchPilotEvidenceError(f"cannot read {path}") from error
    if not isinstance(value, dict):
        raise ResearchPilotEvidenceError(f"{path} must contain an object")
    return value


def _artifact_receipt(item: object) -> _ArtifactReceipt:
    if not isinstance(item, dict):
        raise ResearchPilotEvidenceError("package artifact receipt is invalid")
    kind = item.get("kind")
    filename = item.get("filename")
    size = item.get("bytes")
    digest = item.get("sha256")
    members = item.get("members")
    if (
        kind not in {"wheel", "sdist"}
        or type(filename) is not str
        or Path(filename).name != filename
        or type(size) is not int
        or not 0 < size <= MAX_ARTIFACT_BYTES
        or type(digest) is not str
        or len(digest) != SHA256_LENGTH
        or type(members) is not int
        or members <= 0
    ):
        raise ResearchPilotEvidenceError("package artifact receipt is unsafe")
    return _ArtifactReceipt(kind, filename, size, digest, members)


def _verify_external_artifact(root: Path, receipt: _ArtifactReceipt) -> None:
    path = (root / receipt.filename).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ResearchPilotEvidenceError("package artifact escapes artifact directory") from error
    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise ResearchPilotEvidenceError("package artifact is unavailable") from error
    if file_size > MAX_ARTIFACT_BYTES:
        raise ResearchPilotEvidenceError("package artifact exceeds the bounded size")
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_ARTIFACT_BYTES + 1)
    except OSError as error:
        raise ResearchPilotEvidenceError("package artifact is unavailable") from error
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ResearchPilotEvidenceError("package artifact exceeds the bounded size")
    if len(payload) != receipt.size or hashlib.sha256(payload).hexdigest() != receipt.digest:
        raise ResearchPilotEvidenceError("package artifact bytes do not match receipt")
    try:
        if receipt.kind == "wheel":
            with zipfile.ZipFile(path) as archive:
                members = len(archive.namelist())
        else:
            with tarfile.open(path) as archive:
                members = len(archive.getnames())
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ResearchPilotEvidenceError("package artifact archive is unreadable") from error
    if members != receipt.members:
        raise ResearchPilotEvidenceError("package artifact member count differs")


def _verify_package(evidence_root: Path, artifacts_root: Path | None) -> dict[str, object]:
    package = _read(evidence_root, "package.json")
    if (
        package.get("module_id") != MODULE
        or package.get("source_date_epoch") != SOURCE_DATE_EPOCH
        or package.get("reproducible_builds") is not True
        or package.get("isolated_import") is not True
    ):
        raise ResearchPilotEvidenceError("package reproducibility evidence is not closed")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != EXPECTED_ARTIFACTS:
        raise ResearchPilotEvidenceError("package must contain wheel and sdist receipts")
    receipts = [_artifact_receipt(item) for item in artifacts]
    kinds = {receipt.kind for receipt in receipts}
    if kinds != {"wheel", "sdist"}:
        raise ResearchPilotEvidenceError("package artifact kinds are incomplete")
    for receipt in receipts:
        if artifacts_root is None:
            continue
        root = artifacts_root.resolve()
        _verify_external_artifact(root, receipt)
    return {"passed": True, "artifacts": [receipt.kind for receipt in receipts]}


def verify(root: Path = Path(), artifacts_root: Path | None = None) -> dict[str, object]:
    """Verify policy, evaluation, benchmark, and scoped coverage receipts."""

    evidence_root = root / "docs/evidence/research_pilot"
    manifest = _read(evidence_root, "manifest.json")
    coverage = _read(evidence_root, "coverage.json")
    evaluation = _read(evidence_root, "evaluation.json")
    benchmark = _read(evidence_root, "benchmark.json")
    package = _verify_package(evidence_root, artifacts_root)
    if manifest.get("module_id") != MODULE or manifest.get("no_network") is not True:
        raise ResearchPilotEvidenceError("manifest identity or network policy is invalid")
    for field in (
        "no_clinical_claims",
        "no_disease_claims",
        "no_treatment_claims",
        "owner_review_required",
        "result_digest_replay_bound",
    ):
        if manifest.get(field) is not True:
            raise ResearchPilotEvidenceError(f"manifest policy {field} is not closed")
    if (
        coverage.get("module_id") != MODULE
        or coverage.get("branch_enabled") is not True
        or coverage.get("passed") is not True
        or float(coverage.get("branch_coverage_percent", 0.0))
        < float(coverage.get("fail_under", 95.0))
    ):
        raise ResearchPilotEvidenceError("coverage evidence does not meet the gate")
    if evaluation.get("module_id") != MODULE or evaluation.get("passed") is not True:
        raise ResearchPilotEvidenceError("evaluation evidence did not pass")
    scenarios = evaluation.get("scenarios")
    if not isinstance(scenarios, dict) or scenarios.get("replay", {}).get("passed") is not True:
        raise ResearchPilotEvidenceError("replay scenario evidence is incomplete")
    if (
        benchmark.get("module_id") != MODULE
        or benchmark.get("passed") is not True
        or float(benchmark.get("mean_ns", 0)) > float(benchmark["budgets_ns"]["mean"])
        or float(benchmark.get("p95_ns", 0)) > float(benchmark["budgets_ns"]["p95"])
    ):
        raise ResearchPilotEvidenceError("benchmark evidence does not meet the budgets")
    return {
        "module_id": MODULE,
        "coverage_percent": coverage["branch_coverage_percent"],
        "tests": coverage["test_count"],
        "benchmark_mean_ns": benchmark["mean_ns"],
        "benchmark_p95_ns": benchmark["p95_ns"],
        "package": package,
        "passed": True,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify(artifacts_root=arguments.artifacts_dir), sort_keys=True))
