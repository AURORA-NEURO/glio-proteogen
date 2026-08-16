"""Release-evidence verifier tests for M12-07."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.verify_m1207_release import (
    M1207ReleaseVerificationError,
    verify_release,
)


def test_m1207_release_evidence_verifies_without_artifact_directory() -> None:
    verify_release()


def test_m1207_release_evidence_verifies_built_artifacts() -> None:
    verify_release(Path(r"C:\Users\murar\AppData\Local\Temp\gpa-m1207-dist-clean"))


def test_m1207_release_verifier_rejects_missing_artifact_directory(tmp_path: Path) -> None:
    with pytest.raises(M1207ReleaseVerificationError, match="missing package artifact"):
        verify_release(tmp_path)
