"""Release evidence verifier tests for M06-08."""

from __future__ import annotations

from pathlib import Path

from tools.verify_m0608_evidence import verify_evidence

_CHECK_COUNT = 8


def test_committed_m0608_evidence_closure_passes() -> None:
    root = Path(__file__).parents[2]
    report = verify_evidence(root / "release-evidence/m06_08")
    assert report["module_id"] == "GLIO-PROTEOGEN-M06-08"
    assert report["passed"] is True
    assert report["evaluation_checks"] == _CHECK_COUNT
