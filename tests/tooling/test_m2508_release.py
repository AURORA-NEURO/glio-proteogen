"""Independent M25-08 release-evidence verifier tests."""

from pathlib import Path

from tools.verify_m2508_release import verify


def test_release_evidence_verifies_without_package_artifacts() -> None:
    report = verify(Path(__file__).parents[2])
    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())
