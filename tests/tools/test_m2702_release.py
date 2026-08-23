"""Independent release-evidence checks for M27-02."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m2702_release import ReleaseVerificationError, verify

_MIN_COVERAGE = 95.0


def test_m2702_release_evidence_matches_current_packages() -> None:
    root = Path(__file__).parents[2]
    report = verify(root / "release-evidence" / "m27_02", root / "dist")

    assert report["verified"] is True
    assert report["module_id"] == "GLIO-PROTEOGEN-M27-02"
    assert report["coverage"] >= _MIN_COVERAGE


def test_m2702_release_evidence_rejects_stale_package_digest(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    evidence = root / "release-evidence" / "m27_02"
    copied = tmp_path / "m27_02"
    copied.mkdir()
    for name in ("evaluation.json", "benchmark.json", "coverage.json", "package.json"):
        (copied / name).write_bytes((evidence / name).read_bytes())

    package_path = copied / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["wheel"]["sha256"] = "0" * 64
    package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(ReleaseVerificationError, match="package digest mismatch"):
        verify(copied, root / "dist")
