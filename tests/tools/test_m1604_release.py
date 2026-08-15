"""Release-evidence verifier tests for M16-04."""

# ruff: noqa: PLR2004

from tools.verify_m1604_release import verify_release


def test_m1604_release_evidence_is_closed() -> None:
    result = verify_release()
    assert result["module_id"] == "GLIO-PROTEOGEN-M16-04"
    assert result["declared_cases"] == result["executed_cases"] == 6
    assert result["passed"] is True

