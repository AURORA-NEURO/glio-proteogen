"""Release verifier tests for M25-05 evidence."""

from pathlib import Path
from typing import cast

from tools.verify_m2505_release import verify


def test_m2505_release_evidence_passes_without_package() -> None:
    root = Path(__file__).parents[2]

    report = verify(root)

    assert report["passed"] is True
    checks = cast("dict[str, bool]", report["checks"])
    assert all(checks.values())
