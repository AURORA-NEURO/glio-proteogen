"""Release-evidence verifier tests for M11-08."""

from tools.verify_m1108_release import verify_release


def test_m1108_release_evidence_verifies() -> None:
    report = verify_release()
    assert report["module"] == "GLIO-PROTEOGEN-M11-08"
    assert report["passed"] is True
