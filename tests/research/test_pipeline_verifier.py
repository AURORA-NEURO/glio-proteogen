"""Adversarial checks for research evaluator/release evidence verification."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from tools.verify_research_pipeline import (
    VerificationError,
    _require_installed_research_runtime,
    _verify_benchmark_record,
    _verify_package,
    verify,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _ROOT / "docs" / "evidence" / "research-foundation" / "evaluation.json"
_PACKAGE = _ROOT / "docs" / "evidence" / "research-foundation" / "package.json"


def _write_mutation(tmp_path: Path, mutate: Callable[[dict[str, object]], None]) -> Path:
    value = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    mutate(value)
    output = tmp_path / "evaluation.json"
    output.write_text(json.dumps(value), encoding="utf-8")
    return output


def test_research_evidence_verifier_accepts_locked_record() -> None:
    verify(_EVIDENCE, allow_metadata_only=True)


def test_research_evidence_verifier_requires_artifacts_by_default() -> None:
    with pytest.raises(VerificationError, match="wheel and sdist"):
        verify(_EVIDENCE)


def test_artifact_bound_replay_rejects_source_checkout_runtime() -> None:
    with pytest.raises(VerificationError, match="installed wheel"):
        _require_installed_research_runtime()


def test_research_evidence_verifier_rejects_fixture_digest_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        value["fixture_sha256"] = "0" * 64

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="fixture digest"):
        verify(evidence, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_scenario_inventory_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        evaluator = value["evaluator"]
        assert isinstance(evaluator, dict)
        evaluator["scenario_ids"] = ["target_supported"]

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="scenario inventory"):
        verify(evidence, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_cohort_projection_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        cohort = value["cohort_evaluation"]
        assert isinstance(cohort, dict)
        outcomes = cohort["outcomes"]
        assert isinstance(outcomes, list)
        projection = outcomes[0]["projection"]
        assert isinstance(projection, dict)
        matrix = projection["matrix"]
        assert isinstance(matrix, list)
        matrix[0][1][0] = 999.0

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="cohort outcome projections"):
        verify(evidence, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_cohort_provenance_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        cohort = value["cohort_evaluation"]
        assert isinstance(cohort, dict)
        outcomes = cohort["outcomes"]
        assert isinstance(outcomes, list)
        projection = outcomes[-1]["projection"]
        assert isinstance(projection, dict)
        configuration = projection["configuration"]
        assert isinstance(configuration, dict)
        provenance = configuration["sample_source_provenance"]
        assert isinstance(provenance, list)
        provenance[0]["external_source_id"] = "pdc:forged"

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="cohort outcome projections"):
        verify(evidence, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_package_hash_receipt_mutation(
    tmp_path: Path,
) -> None:
    package = json.loads(_PACKAGE.read_text(encoding="utf-8"))
    verification = package["verification"]
    assert isinstance(verification, dict)
    wheel = verification["wheel"]
    assert isinstance(wheel, dict)
    wheel["sha256"] = "not-a-sha"
    mutated = tmp_path / "package.json"
    mutated.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(VerificationError, match=r"sha256|SHA-256|receipt"):
        verify(_EVIDENCE, package_evidence=mutated, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_non_reproducible_receipt(
    tmp_path: Path,
) -> None:
    package = json.loads(_PACKAGE.read_text(encoding="utf-8"))
    package["verification"]["reproducible_builds"] = 1
    mutated = tmp_path / "package.json"
    mutated.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(VerificationError, match="two reproducible builds"):
        verify(_EVIDENCE, package_evidence=mutated, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_reproducibility_hash_drift(
    tmp_path: Path,
) -> None:
    package = json.loads(_PACKAGE.read_text(encoding="utf-8"))
    verification = package["verification"]
    assert isinstance(verification, dict)
    hashes = verification["reproducible_hashes"]
    assert isinstance(hashes, dict)
    hashes["wheel"] = "0" * 64
    mutated = tmp_path / "package.json"
    mutated.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(VerificationError, match="reproducibility hashes"):
        verify(_EVIDENCE, package_evidence=mutated, allow_metadata_only=True)


def test_research_evidence_verifier_rejects_package_fixture_drift(tmp_path: Path) -> None:
    package = json.loads(_PACKAGE.read_text(encoding="utf-8"))
    verification = package["verification"]
    assert isinstance(verification, dict)
    verification["fixture_sha256"] = "0" * 64
    mutated = tmp_path / "package.json"
    mutated.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(VerificationError, match="package fixture digest"):
        verify(_EVIDENCE, package_evidence=mutated, allow_metadata_only=True)


def test_research_benchmark_rejects_nonfinite_exponent_value() -> None:
    record = {
        "iterations": 10,
        "percentile_method": "nearest_rank",
        "samples_ns": list(range(1, 11)),
        "mean_ns": float("inf"),
        "median_ns": 6,
        "p95_ns": 10,
    }
    with pytest.raises(VerificationError, match="mean_ns"):
        _verify_benchmark_record(record)


def test_research_benchmark_recomputes_nearest_rank_p95() -> None:
    record = {
        "iterations": 10,
        "percentile_method": "nearest_rank",
        "samples_ns": list(range(1, 11)),
        "mean_ns": 5.5,
        "median_ns": 6,
        "p95_ns": 9,
    }
    with pytest.raises(VerificationError, match="p95"):
        _verify_benchmark_record(record)


def test_research_package_verifier_binds_artifact_size_hash_and_members(tmp_path: Path) -> None:
    artifact = tmp_path / "research.whl"
    with ZipFile(artifact, "w") as archive:
        archive.writestr("glio_proteogen/research/pipeline.py", "")
        archive.writestr("glio_proteogen/research/search.py", "")
        archive.writestr("glio_proteogen/research/protein.py", "")
        archive.writestr("glio_proteogen/research/cohort.py", "")
    digest = sha256(artifact.read_bytes()).hexdigest()
    receipt = {"filename": artifact.name, "bytes": artifact.stat().st_size, "sha256": digest}
    _verify_package(artifact, receipt)
    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(VerificationError, match=r"size|SHA-256"):
        _verify_package(artifact, receipt)
