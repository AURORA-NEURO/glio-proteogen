"""Release evidence verifier tests for M11-06."""

from pathlib import Path

import pytest
from tools.verify_m1106_release import (
    M1106ReleaseVerificationError,
    verify_release,
)


def test_release_evidence_verifies() -> None:
    root = Path(__file__).parents[2]
    report = verify_release(root)
    assert report["module_id"] == "GLIO-PROTEOGEN-M11-06"
    assert report["passed"] is True


def test_release_verifier_rejects_missing_evidence(tmp_path: Path) -> None:
    with pytest.raises(M1106ReleaseVerificationError, match="cannot read"):
        verify_release(tmp_path)
