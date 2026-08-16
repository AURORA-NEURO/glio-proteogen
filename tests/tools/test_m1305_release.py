"""Release-evidence verifier tests for M13-05."""

import pytest
from tools.verify_m1305_release import (
    CASE_IDS,
    FIXTURE_DIGEST,
    _verify_benchmark,
    _verify_evaluation,
    verify_release,
)


def test_m1305_release_evidence_verifies() -> None:
    assert verify_release() == {
        "module_id": "GLIO-PROTEOGEN-M13-05",
        "evaluation": True,
        "benchmark": True,
        "coverage": True,
        "package": True,
    }


def test_m1305_evaluation_rejects_fixture_or_case_tamper() -> None:
    case_ids = list(CASE_IDS)
    fixture = {
        "module_id": "GLIO-PROTEOGEN-M13-05",
        "fixture_sha256": FIXTURE_DIGEST,
        "case_ids": case_ids,
        "declared_cases": 7,
        "executed_cases": 7,
        "passed_cases": 7,
        "passed": True,
    }
    case_ids[0] = "tampered"
    with pytest.raises(ValueError, match="case IDs"):
        _verify_evaluation(fixture)
    with pytest.raises(ValueError, match="budget"):
        _verify_benchmark(
            {
                "module_id": "GLIO-PROTEOGEN-M13-05",
                "iterations": 1,
                "mean_ns": 4,
                "p95_ns": 4,
                "mean_budget_ns": 3,
                "p95_budget_ns": 3,
                "passed": False,
            }
        )
