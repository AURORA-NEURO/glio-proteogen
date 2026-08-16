"""Release-evidence verifier gate for M11-02."""

from pathlib import Path

from tools.verify_m1102_release import verify


def test_m1102_release_evidence_is_complete() -> None:
    verify(Path("release-evidence/m11_02"))
