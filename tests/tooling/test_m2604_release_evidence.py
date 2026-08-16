"""Release-evidence verifier tests for M26-04."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_release_artifacts import ReleaseArtifactError, verify_m2604_evidence

_ROOT = Path(__file__).parents[2]
_EVIDENCE = _ROOT / "release-evidence" / "m26_04"


def test_m2604_release_evidence_verifies() -> None:
    verify_m2604_evidence(_EVIDENCE / "evaluation.json", _EVIDENCE / "benchmark.json")


def test_m2604_release_evidence_rejects_wrong_identity(tmp_path: Path) -> None:
    payload = json.loads((_EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    payload["moduleId"] = "GLIO-PROTEOGEN-FORGED"
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="wrong module identity"):
        verify_m2604_evidence(evaluation, _EVIDENCE / "benchmark.json")


def test_m2604_release_evidence_rejects_wrong_sample_count(tmp_path: Path) -> None:
    payload = json.loads((_EVIDENCE / "benchmark.json").read_text(encoding="utf-8"))
    payload["samplesNs"] = payload["samplesNs"][:-1]
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseArtifactError, match="invalid samples"):
        verify_m2604_evidence(_EVIDENCE / "evaluation.json", benchmark)
