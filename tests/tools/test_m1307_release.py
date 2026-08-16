"""Release-evidence verifier tests for M13-07."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1307_release import (
    M1307ReleaseVerificationError,
    _verify_benchmark,
    _verify_evaluation,
    verify_release,
)


def test_release_evidence_verifies_current_artifacts() -> None:
    report = verify_release()
    assert report["module_id"] == "GLIO-PROTEOGEN-M13-07"
    assert all(report[key] is True for key in ("evaluation", "benchmark", "package"))


def test_evaluation_rejects_wrong_fixture_digest() -> None:
    value = json.loads(
        (Path("release-evidence/m13_07/evaluation.json")).read_text(encoding="utf-8")
    )
    value["fixture_digest"] = "sha256:" + "0" * 64
    with pytest.raises(M1307ReleaseVerificationError):
        _verify_evaluation(value)


def test_benchmark_rejects_budget_overrun() -> None:
    with pytest.raises(M1307ReleaseVerificationError):
        _verify_benchmark(
            {
                "module_id": "GLIO-PROTEOGEN-M13-07",
                "mean_ns": 2,
                "p95_ns": 3,
                "mean_budget_ns": 1,
                "p95_budget_ns": 3,
                "within_budget": False,
            }
        )
