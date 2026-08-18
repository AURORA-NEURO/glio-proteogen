"""Adversarial checks for research evaluator/release evidence verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tools.verify_research_pipeline import VerificationError, verify

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
    verify(_EVIDENCE)


def test_research_evidence_verifier_rejects_fixture_digest_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        value["fixture_sha256"] = "0" * 64

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="fixture digest"):
        verify(evidence)


def test_research_evidence_verifier_rejects_scenario_inventory_mutation(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        evaluator = value["evaluator"]
        assert isinstance(evaluator, dict)
        evaluator["scenario_ids"] = ["target_supported"]

    evidence = _write_mutation(tmp_path, mutate)
    with pytest.raises(VerificationError, match="scenario inventory"):
        verify(evidence)


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
        verify(_EVIDENCE, package_evidence=mutated)


def test_research_evidence_verifier_rejects_non_reproducible_receipt(
    tmp_path: Path,
) -> None:
    package = json.loads(_PACKAGE.read_text(encoding="utf-8"))
    package["verification"]["reproducible_builds"] = 1
    mutated = tmp_path / "package.json"
    mutated.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(VerificationError, match="two reproducible builds"):
        verify(_EVIDENCE, package_evidence=mutated)
