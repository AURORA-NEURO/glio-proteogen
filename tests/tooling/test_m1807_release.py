"""Release-evidence verifier tests for M18-07."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_m1807_release import (
    M1807ReleaseEvidenceError,
    verify_benchmark,
    verify_coverage,
    verify_evaluation,
    verify_fixture,
    verify_package,
    verify_release,
)

_EVIDENCE = Path(__file__).parents[2] / "release-evidence" / "m18_07"
_DIST = Path(__file__).parents[2] / "dist-m18-07"
_FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m18_07" / "scenarios.json"


def test_release_evidence_verifier_accepts_frozen_evaluation_benchmark_coverage() -> None:
    verify_evaluation(_EVIDENCE / "evaluation.json")
    verify_benchmark(_EVIDENCE / "benchmark.json")
    verify_coverage(_EVIDENCE / "coverage.json")
    verify_fixture(_FIXTURE)


def test_release_verifier_accepts_package_hashes_and_isolated_import() -> None:
    verify_package(_EVIDENCE / "package.json", _DIST)
    verify_release(_EVIDENCE, _DIST, _FIXTURE)


def test_release_verifier_rejects_tampered_package_hash(tmp_path: Path) -> None:
    package = json.loads((_EVIDENCE / "package.json").read_text(encoding="utf-8"))
    package["wheel"]["sha256"] = "0" * 64
    tampered = tmp_path / "package.json"
    tampered.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(M1807ReleaseEvidenceError):
        verify_package(tampered, _DIST)


@pytest.mark.parametrize("filename", ["evaluation.json", "benchmark.json", "coverage.json"])
def test_release_evidence_verifier_rejects_tampered_reports(
    filename: str,
    tmp_path: Path,
) -> None:
    source = _EVIDENCE / filename
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["module_id"] = "GLIO-PROTEOGEN-M00-00"
    target = tmp_path / filename
    target.write_text(json.dumps(payload), encoding="utf-8")
    verifier = {
        "evaluation.json": verify_evaluation,
        "benchmark.json": verify_benchmark,
        "coverage.json": verify_coverage,
    }[filename]
    with pytest.raises(M1807ReleaseEvidenceError):
        verifier(target)
