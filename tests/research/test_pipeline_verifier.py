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
