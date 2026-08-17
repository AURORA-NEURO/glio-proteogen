"""Machine-readable M28-04 release evidence verification."""

from tools.verify_m2804_evidence import verify

EXPECTED_CHECKS = 10


def test_m2804_release_evidence_is_cross_bound() -> None:
    report = verify()
    assert report["module_id"] == "GLIO-PROTEOGEN-M28-04"
    assert report["evaluator_checks"] == EXPECTED_CHECKS
    assert report["generated_member_count"] == 0
    assert report["unsafe_path_count"] == 0
    assert report["passed"] is True
