"""Release-evidence verifier tests for M16-01."""

# ruff: noqa: PLR2004

from tools.verify_m1601_release import verify_release


def test_m1601_release_evidence_is_closed() -> None:
    result = verify_release()
    assert result["module_id"] == "GLIO-PROTEOGEN-M16-01"
    assert result["declared_cases"] == result["executed_cases"] == 6
    assert result["passed"] is True
