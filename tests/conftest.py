"""Shared test policy for artifacts supplied outside the source checkout."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_HISTORICAL_ARTIFACT_BY_TEST_FILE = {
    "test_m1003_release.py": "dist-m10-03",
    "test_m1104_release.py": "dist-m11-04",
    "test_m1106_release.py": "dist-m11-06",
    "test_m1107_release.py": "dist-m11-07",
    "test_m1108_release.py": "dist-m11_08",
    "test_m1204_release.py": "dist-m12-04",
    "test_m1205_release.py": "dist-m12-05",
    "test_m1207_release.py": "dist-m12-07",
    "test_m1208_release.py": "dist-m12-08",
    "test_m13_02_release.py": "dist-m13-02",
    "test_m1304_release.py": "dist-m13-04",
    "test_m1305_release.py": "dist-m13-05",
    "test_m1404_release.py": "dist-m14-04",
    "test_m1406_release.py": "dist-m14-06",
    "test_m1408_release.py": "dist-m14-08",
    "test_m1503_release.py": "dist-m15-03",
    "test_m1506_release.py": "dist-m15-06",
    "test_m1601_release.py": "dist-m16-01",
    "test_m1604_release.py": "dist-m16-04",
    "test_m1807_release.py": "dist-m18-07",
    "test_m2002_release.py": "dist-m20-02",
    "test_m2502_release.py": "dist-m25-02",
    "test_m2504_release.py": "dist-m25-04",
    "test_m2702_release.py": "dist-m27-02",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip only acceptance tests whose immutable historical bundles are absent."""

    for item in items:
        if "historical_artifact" not in item.keywords:
            continue
        test_file = Path(str(item.path)).name
        artifact_dir = _HISTORICAL_ARTIFACT_BY_TEST_FILE.get(test_file)
        if artifact_dir is None:
            message = f"historical_artifact test {test_file} has no registered bundle"
            raise pytest.UsageError(message)
        if not (_REPOSITORY_ROOT / artifact_dir).is_dir():
            item.add_marker(
                pytest.mark.skip(reason=f"historical release bundle unavailable: {artifact_dir}")
            )
