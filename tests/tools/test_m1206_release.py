"""Release evidence verifier tests for M12-06."""

from tools.verify_m1206_release import verify_release


def test_m1206_release_evidence_verifies() -> None:
    assert verify_release() == {"module_id": "GLIO-PROTEOGEN-M12-06", "passed": True}
