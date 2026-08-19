"""Independent release-evidence checks for M25-06."""

from __future__ import annotations

from pathlib import Path

from tools.verify_m2506_release import verify


def test_m2506_release_evidence_is_internally_consistent() -> None:
    root = Path(__file__).parents[2]
    report = verify(root)
    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(value is True for value in checks.values())
