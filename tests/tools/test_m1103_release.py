"""Release evidence verifier tests for M11-03."""

from tools.verify_m1103_release import verify_release


def test_m1103_release_evidence_verifies() -> None:
    report = verify_release()
    assert report["module_id"] == "GLIO-PROTEOGEN-M11-03"
    assert report["passed"] is True
