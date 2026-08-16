"""Adversarial tests for the M14-07 release evidence verifier."""

from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING

import pytest
from tools.verify_m1407_release import (
    CASE_IDS,
    FIXTURE_DIGEST,
    M1407ReleaseEvidenceError,
    verify_benchmark,
    verify_coverage,
    verify_evaluation,
    verify_package,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _evaluation() -> dict[str, object]:
    return {
        "module_id": "GLIO-PROTEOGEN-M14-07",
        "fixture_digest": FIXTURE_DIGEST,
        "declared_cases": 9,
        "executed_cases": 9,
        "passed_cases": 9,
        "total_cases": 9,
        "passed": True,
        "checks": [{"name": name, "passed": True} for name in CASE_IDS],
    }


def _benchmark() -> dict[str, object]:
    return {
        "module_id": "GLIO-PROTEOGEN-M14-07",
        "iterations": 10,
        "mean_ns": 100,
        "median_ns": 100,
        "p95_ns": 200,
        "mean_budget_ns": 2_000_000_000,
        "p95_budget_ns": 3_000_000_000,
        "passed": True,
    }


def _coverage() -> dict[str, object]:
    return {
        "module_id": "GLIO-PROTEOGEN-M14-07",
        "branch": True,
        "branch_percent": 98.0,
        "fail_under": 95.0,
        "statements": 479,
        "covered_statements": 470,
        "branches": 78,
        "covered_branches": 75,
    }


def test_evaluation_benchmark_and_coverage_verifiers_accept_locked_shapes(tmp_path: Path) -> None:
    evaluation = tmp_path / "evaluation.json"
    benchmark = tmp_path / "benchmark.json"
    coverage = tmp_path / "coverage.json"
    _write(evaluation, _evaluation())
    _write(benchmark, _benchmark())
    _write(coverage, _coverage())
    verify_evaluation(evaluation)
    verify_benchmark(benchmark)
    verify_coverage(coverage)


def test_verifiers_reject_tampering(tmp_path: Path) -> None:
    evaluation = _evaluation()
    evaluation["fixture_digest"] = "sha256:bad"
    path = tmp_path / "evaluation.json"
    _write(path, evaluation)
    with pytest.raises(M1407ReleaseEvidenceError):
        verify_evaluation(path)
    benchmark = _benchmark()
    benchmark["p95_ns"] = 3_000_000_001
    path = tmp_path / "benchmark.json"
    _write(path, benchmark)
    with pytest.raises(M1407ReleaseEvidenceError):
        verify_benchmark(path)
    coverage = _coverage()
    coverage["branch"] = False
    path = tmp_path / "coverage.json"
    _write(path, coverage)
    with pytest.raises(M1407ReleaseEvidenceError):
        verify_coverage(path)


def test_package_verifier_checks_hash_size_members_and_import(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "glio_proteogen-0.1.0-py3-none-any.whl"
    sdist = dist / "glio-proteogen-0.1.0.tar.gz"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("glio_proteogen/__init__.py", "__version__ = '0.1.0'\n")
    sdist.write_bytes(b"fixture")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    report = {
        "module_id": "GLIO-PROTEOGEN-M14-07",
        "wheel": {
            "filename": wheel.name,
            "sha256": digest(wheel),
            "size_bytes": wheel.stat().st_size,
            "member_count": 1,
        },
        "sdist": {
            "filename": sdist.name,
            "sha256": digest(sdist),
            "size_bytes": sdist.stat().st_size,
        },
        "isolated_import": True,
    }
    evidence = tmp_path / "package.json"
    _write(evidence, report)
    verify_package(evidence, dist)
    report["wheel"]["sha256"] = "0" * 64  # type: ignore[index]
    _write(evidence, report)
    with pytest.raises(M1407ReleaseEvidenceError):
        verify_package(evidence, dist)
