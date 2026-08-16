"""Executable M13-02 release-evidence verifier tests."""

from pathlib import Path

import pytest
from tools.verify_m13_02_release import (
    M1302ReleaseVerificationError,
    verify_release,
)


def test_m13_02_release_evidence_verifies() -> None:
    root = Path(__file__).parents[2]
    report = verify_release(root / "dist-m13-02")
    assert report["module_id"] == "GLIO-PROTEOGEN-M13-02"
    assert report["verified"] is True


def test_m13_02_release_verifier_rejects_missing_package(tmp_path: Path) -> None:
    with pytest.raises(M1302ReleaseVerificationError, match="missing artifact"):
        verify_release(tmp_path)
