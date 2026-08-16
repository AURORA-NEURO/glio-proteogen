"""Release-evidence verifier tests for M18-04."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1804_release import (
    M1804ReleaseEvidenceError,
    verify_benchmark,
    verify_coverage,
    verify_evaluation,
)

_EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m18_04"


def test_release_evidence_verifier_accepts_frozen_evaluation_benchmark_coverage() -> None:
    verify_evaluation(_EVIDENCE / "evaluation.json")
    verify_benchmark(_EVIDENCE / "benchmark.json")
    verify_coverage(_EVIDENCE / "coverage.json")


@pytest.mark.parametrize("filename", ["evaluation.json", "benchmark.json", "coverage.json"])
def test_release_evidence_verifier_rejects_tampered_reports(
    filename: str,
    tmp_path: Path,
) -> None:
    source = _EVIDENCE / filename
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["module_id"] = "GLIO-PROTEOGEN-M00-00"
    target = tmp_path / filename
    target.write_text(json.dumps(payload), encoding="utf-8")
    verifier = {
        "evaluation.json": verify_evaluation,
        "benchmark.json": verify_benchmark,
        "coverage.json": verify_coverage,
    }[filename]
    with pytest.raises(M1804ReleaseEvidenceError):
        verifier(target)
