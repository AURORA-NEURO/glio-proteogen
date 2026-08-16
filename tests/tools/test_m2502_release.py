"""Independent release-evidence checks for M25-02."""

from __future__ import annotations

from pathlib import Path

from tools.verify_m2502_release import verify


def test_m2502_release_evidence_is_internally_consistent() -> None:
    root = Path(__file__).parents[2]
    wheel = root / "dist" / "glio_proteogen-0.1.0-py3-none-any.whl"
    sdist = root / "dist" / "glio_proteogen-0.1.0.tar.gz"
    report = verify(root, wheel, sdist)
    assert report["passed"] is True
    checks = report["checks"]
    assert isinstance(checks, dict)
    assert all(value is True for value in checks.values())
