"""Release-evidence verifier tests for M15-06."""

# ruff: noqa: PLR2004

import pytest
from tools.verify_m1506_release import verify_release


@pytest.mark.historical_artifact
def test_m1506_release_evidence_is_closed_against_historical_artifacts() -> None:
    result = verify_release()
    assert result["module_id"] == "GLIO-PROTEOGEN-M15-06"
    assert result["declared_cases"] == result["executed_cases"] == 7
    assert result["passed"] is True
