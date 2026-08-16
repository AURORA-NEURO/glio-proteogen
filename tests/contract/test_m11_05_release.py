"""Release evidence verifier tests for M11-05."""

from pathlib import Path

import pytest
from tools.verify_m1105_release import (
    M1105ReleaseVerificationError,
    verify_release,
)


def test_release_evidence_verifies() -> None:
    result = verify_release(Path())
    assert result == {"module_id": "GLIO-PROTEOGEN-M11-05", "passed": True}


def test_release_verifier_rejects_missing_package(tmp_path: Path) -> None:
    with pytest.raises(M1105ReleaseVerificationError):
        verify_release(tmp_path)
