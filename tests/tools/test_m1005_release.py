"""Strict release-evidence verifier tests for M10-05."""

import json
from pathlib import Path

import pytest
from tools.verify_m1005_release import M1005ReleaseEvidenceError, verify_evidence


def _bundle(tmp_path: Path) -> Path:
    directory = tmp_path / "evidence"
    directory.mkdir()
    evaluation = {
        "module_id": "GLIO-PROTEOGEN-M10-05",
        "authority_lines": "3452-3495",
        "authority_sha256": "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181",
        "passed": True,
        "check_count": 8,
        "checks": [{"id": str(index), "passed": True} for index in range(8)],
    }
    benchmark = {
        "module_id": "GLIO-PROTEOGEN-M10-05",
        "passed": True,
        "deterministic": True,
        "mean_ns": 10,
        "p95_ns": 20,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
    }
    (directory / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    (directory / "benchmark.json").write_text(json.dumps(benchmark), encoding="utf-8")
    return directory


def test_m1005_release_evidence_passes(tmp_path: Path) -> None:
    report = verify_evidence(_bundle(tmp_path))
    assert report["verified"] is True


@pytest.mark.parametrize("field", ["module_id", "authority_lines", "authority_sha256", "passed"])
def test_m1005_release_evidence_rejects_evaluation_tamper(tmp_path: Path, field: str) -> None:
    directory = _bundle(tmp_path)
    evaluation = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    evaluation[field] = "tampered"
    (directory / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    with pytest.raises(M1005ReleaseEvidenceError):
        verify_evidence(directory)


def test_m1005_release_evidence_rejects_budget_overrun(tmp_path: Path) -> None:
    directory = _bundle(tmp_path)
    benchmark = json.loads((directory / "benchmark.json").read_text(encoding="utf-8"))
    benchmark["mean_ns"] = benchmark["mean_budget_ns"] + 1
    (directory / "benchmark.json").write_text(json.dumps(benchmark), encoding="utf-8")
    with pytest.raises(M1005ReleaseEvidenceError):
        verify_evidence(directory)
