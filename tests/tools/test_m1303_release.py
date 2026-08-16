"""Release evidence verifier tests for M13-03."""

from __future__ import annotations

import pytest
from tools.verify_m1303_release import (
    M1303ReleaseVerificationError,
    _verify_benchmark,
    _verify_evaluation,
    verify_release,
)

_EXPECTED_COVERAGE = 98.0


def test_m1303_release_evidence_is_green() -> None:
    report = verify_release()

    assert report["release_passed"] is True
    assert report["coverage_percent"] == _EXPECTED_COVERAGE


def test_m1303_verifier_rejects_bad_evaluation_and_benchmark() -> None:
    with pytest.raises(M1303ReleaseVerificationError, match="fixture digest"):
        _verify_evaluation({"module_id": "GLIO-PROTEOGEN-M13-03", "fixture_digest": "bad"})
    with pytest.raises(M1303ReleaseVerificationError, match="ten iterations"):
        _verify_benchmark({"module_id": "GLIO-PROTEOGEN-M13-03", "iterations": 1})
