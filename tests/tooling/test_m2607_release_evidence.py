"""Release-evidence verifier tests for M26-07."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_release_artifacts import ReleaseArtifactError, verify_m2607_evidence

EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m26_07"


def test_m2607_release_evidence_is_closed() -> None:
    verify_m2607_evidence(EVIDENCE / "evaluation.json", EVIDENCE / "benchmark.json")


def test_m2607_release_evidence_rejects_tampered_authority(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    payload["authority"]["slice"] = "GLIO-PROTEOGEN_240_Module_Dossier.md:1-2"
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReleaseArtifactError, match="authority"):
        verify_m2607_evidence(evaluation, EVIDENCE / "benchmark.json")


def test_m2607_release_evidence_rejects_budget_overrun(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "benchmark.json").read_text(encoding="utf-8"))
    payload["meanNs"] = payload["budgetsNs"]["mean"] + 1
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReleaseArtifactError, match="timing budgets"):
        verify_m2607_evidence(EVIDENCE / "evaluation.json", benchmark)
