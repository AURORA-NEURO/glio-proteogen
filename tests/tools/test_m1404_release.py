"""Release-evidence verifier tests for M14-04."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1404_release import (
    M1404ReleaseVerificationError,
    _verify_benchmark,
    _verify_evaluation,
    verify_release,
)


def test_release_evidence_verifies_current_artifacts() -> None:
    report = verify_release()
    assert report["module_id"] == "GLIO-PROTEOGEN-M14-04"
    assert all(report[key] is True for key in ("evaluation", "benchmark", "coverage", "package"))


def test_evaluation_rejects_wrong_fixture_digest() -> None:
    value = json.loads(
        (Path("release-evidence/m14_04/evaluation.json")).read_text(encoding="utf-8")
    )
    value["fixture_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(M1404ReleaseVerificationError):
        _verify_evaluation(value)


def test_benchmark_rejects_budget_overrun() -> None:
    with pytest.raises(M1404ReleaseVerificationError):
        _verify_benchmark(
            {
                "module_id": "GLIO-PROTEOGEN-M14-04",
                "iterations": 1,
                "mean_ns": 2,
                "p95_ns": 3,
                "mean_budget_ns": 1,
                "p95_budget_ns": 3,
                "passed": False,
            }
        )
