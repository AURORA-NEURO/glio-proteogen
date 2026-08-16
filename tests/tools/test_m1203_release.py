"""Release verifier tests for M12-03 evidence closure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1203_release import (
    M1203ReleaseVerificationError,
    verify_release,
)


def test_m1203_release_verifier_rejects_pending_package(tmp_path: Path) -> None:
    source = Path("release-evidence/m12_03")
    target = tmp_path / "m12_03"
    target.mkdir()
    for name in ("evaluation.json", "benchmark.json", "package.json"):
        (target / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(M1203ReleaseVerificationError, match="hash"):
        verify_release(target)


def test_m1203_release_verifier_rejects_benchmark_budget(tmp_path: Path) -> None:
    source = Path("release-evidence/m12_03")
    target = tmp_path / "m12_03"
    target.mkdir()
    for name in ("evaluation.json", "benchmark.json", "package.json"):
        (target / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    benchmark = json.loads((target / "benchmark.json").read_text(encoding="utf-8"))
    benchmark["passed"] = False
    (target / "benchmark.json").write_text(json.dumps(benchmark), encoding="utf-8")
    with pytest.raises(M1203ReleaseVerificationError, match="benchmark"):
        verify_release(target)
