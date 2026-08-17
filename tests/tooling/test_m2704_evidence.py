"""Machine-readable M27-04 release evidence verification."""

from tools.verify_m2704_evidence import verify

EXPECTED_CHECKS = 10


def test_m2704_release_evidence_is_cross_bound() -> None:
    report = verify()
    assert report["module_id"] == "GLIO-PROTEOGEN-M27-04"
    assert report["evaluator_checks"] == EXPECTED_CHECKS
    assert report["passed"] is True
