"""Release-evidence verifier tests for M07-04."""

from __future__ import annotations

from pathlib import Path

from tools.verify_m0704_evidence import verify_evidence

_CHECK_COUNT = 11


def test_committed_m0704_evidence_closure_passes() -> None:
    root = Path(__file__).parents[2]
    report = verify_evidence(root / "release-evidence/m07_04")
    assert report["module_id"] == "GLIO-PROTEOGEN-M07-04"
    assert report["passed"] is True
    assert report["evaluation_checks"] == _CHECK_COUNT
