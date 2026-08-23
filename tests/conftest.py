"""Shared test policy for artifacts supplied outside the source checkout."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_HISTORICAL_ARTIFACT_DIRS = (
    "dist-m10-03",
    "dist-m11-04",
    "dist-m11_08",
    "dist-m12-04",
    "dist-m12-05",
    "dist-m12-08",
    "dist-m13-02",
    "dist-m13-04",
    "dist-m13-05",
    "dist-m14-04",
    "dist-m14-06",
    "dist-m18-07",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip only acceptance tests whose immutable historical bundles are absent."""

    missing = tuple(
        name for name in _HISTORICAL_ARTIFACT_DIRS if not (_REPOSITORY_ROOT / name).is_dir()
    )
    if not missing:
        return
    reason = "historical release bundles unavailable: " + ", ".join(missing)
    for item in items:
        if "historical_artifact" in item.keywords:
            item.add_marker(pytest.mark.skip(reason=reason))
