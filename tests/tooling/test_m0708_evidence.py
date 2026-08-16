"""Release evidence verifier tests for M07-08."""

from __future__ import annotations

from pathlib import Path

from tools.verify_m0708_release import verify_evidence

EXPECTED_EVALUATION_CHECKS = 7


def test_committed_release_evidence_is_closed() -> None:
    root = Path(__file__).parents[2]
    report = verify_evidence(root / "release-evidence/m07_08")
    assert report["module_id"] == "GLIO-PROTEOGEN-M07-08"
    assert report["passed"] is True
    assert report["evaluation_checks"] == EXPECTED_EVALUATION_CHECKS
