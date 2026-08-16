"""Adversarial tests for the M26-08 release-evidence verifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m2608_release import M2608ReleaseVerificationError, verify_release

EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m26_08"
FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m26_08" / "scenarios.json"


def test_m2608_release_evidence_is_closed() -> None:
    verify_release(
        EVIDENCE / "evaluation.json",
        EVIDENCE / "benchmark.json",
        EVIDENCE / "package.json",
        FIXTURE,
    )


def test_m2608_release_evidence_rejects_tampered_authority(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    payload["dossier_slice"] = "GLIO-PROTEOGEN_240_Module_Dossier.md:1-2"
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="dossier_slice"):
        verify_release(evaluation, EVIDENCE / "benchmark.json", EVIDENCE / "package.json", FIXTURE)


def test_m2608_release_evidence_rejects_budget_overrun(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "benchmark.json").read_text(encoding="utf-8"))
    payload["mean_ns"] = payload["mean_budget_ns"] + 1
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="benchmark exceeds"):
        verify_release(EVIDENCE / "evaluation.json", benchmark, EVIDENCE / "package.json", FIXTURE)


def test_m2608_release_evidence_rejects_incomplete_package(tmp_path: Path) -> None:
    payload = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    payload["isolated_import_passed"] = False
    package = tmp_path / "package.json"
    package.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M2608ReleaseVerificationError, match="isolated_import_passed"):
        verify_release(EVIDENCE / "evaluation.json", EVIDENCE / "benchmark.json", package, FIXTURE)
