"""Independent release-evidence checks for M26-03."""

from pathlib import Path
from typing import cast

from tools.verify_m2603_release import verify


def test_m2603_release_manifests_are_consistent() -> None:
    root = Path(__file__).parents[2]
    report = verify(root)
    assert report["passed"] is True
    checks = cast("dict[str, bool]", report["checks"])
    assert all(checks.values())
