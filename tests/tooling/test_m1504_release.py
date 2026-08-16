"""Adversarial tests for the M15-04 release verifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1504_release import (
    M1504ReleaseEvidenceError,
    verify_benchmark,
    verify_coverage,
    verify_evaluation,
)


def test_m1504_release_verifier_accepts_locked_reports() -> None:
    root = Path(__file__).parents[2]
    evidence = root / "release-evidence" / "m15_04"
    verify_evaluation(evidence / "evaluation.json")
    verify_benchmark(evidence / "benchmark.json")
    verify_coverage(evidence / "coverage.json")


@pytest.mark.parametrize("name", ["evaluation.json", "benchmark.json", "coverage.json"])
def test_m1504_release_verifier_rejects_tampered_report(tmp_path: Path, name: str) -> None:
    root = Path(__file__).parents[2]
    source = root / "release-evidence" / "m15_04" / name
    payload = json.loads(source.read_text(encoding="utf-8"))
    if name == "coverage.json":
        payload["percent"] = 0.0
    else:
        payload["passed"] = False
    target = tmp_path / name
    target.write_text(json.dumps(payload), encoding="utf-8")
    verifier = {
        "evaluation.json": verify_evaluation,
        "benchmark.json": verify_benchmark,
        "coverage.json": verify_coverage,
    }[name]
    with pytest.raises(M1504ReleaseEvidenceError):
        verifier(target)
