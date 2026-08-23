"""Release-evidence verifier tests for M11-08."""

import pytest
from tools.verify_m1108_release import verify_release


@pytest.mark.historical_artifact
def test_m1108_release_evidence_verifies() -> None:
    report = verify_release()
    assert report["module"] == "GLIO-PROTEOGEN-M11-08"
    assert report["passed"] is True
