"""Release-evidence verifier tests for M14-08."""

# ruff: noqa: PLR2004

from tools.verify_m1408_release import verify_release


def test_m1408_release_evidence_is_closed() -> None:
    result = verify_release()
    assert result["module_id"] == "GLIO-PROTEOGEN-M14-08"
    assert result["declared_cases"] == result["executed_cases"] == 7
    assert result["passed"] is True
