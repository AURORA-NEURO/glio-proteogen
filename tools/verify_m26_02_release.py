# ruff: noqa: TRY003, T201
"""Independently verify M26-02 release evidence and distribution contents.

The verifier intentionally uses only the Python standard library.  It is an
evidence-consistency check: it does not re-run the evaluator, and it does not
authenticate the caller-declared M26-01 media boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile, ZipFile

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_ID = "GLIO-PROTEOGEN-M26-02"
CONTRACT_VERSION = "0.1.0-provisional"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
MIN_COVERAGE = 95.0
EXPECTED_SCENARIOS = 7
MIN_BENCHMARK_SAMPLES = 10
EXPECTED_WHEEL_MEMBER = (
    "glio_proteogen/modules/c26_proteomics/m26_02_data_model_lineage_service/engine.py"
)


class M2602ReleaseError(ValueError):
    """Raised when release evidence is absent or internally inconsistent."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise M2602ReleaseError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise M2602ReleaseError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise M2602ReleaseError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise M2602ReleaseError(f"{label} must be numeric")
    return float(value)


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise M2602ReleaseError(f"missing distribution: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Mapping[str, object]:
    try:
        with path.open(encoding="utf-8") as stream:
            return _mapping(json.load(stream), str(path))
    except (OSError, json.JSONDecodeError) as error:
        raise M2602ReleaseError(f"cannot read JSON evidence {path}") from error


def _check_identity(document: Mapping[str, object], label: str) -> None:
    if _string(document.get("moduleId"), f"{label}.moduleId") != MODULE_ID:
        raise M2602ReleaseError(f"{label} has the wrong module ID")


def _check_evaluation(document: Mapping[str, object]) -> None:
    _check_identity(document, "evaluation")
    if _string(document.get("contractVersion"), "evaluation.contractVersion") != CONTRACT_VERSION:
        raise M2602ReleaseError("evaluation contract version is not provisional M26-02")
    authority = _mapping(document.get("authority"), "evaluation.authority")
    if (
        _string(authority.get("dossierSha256"), "evaluation.authority.dossierSha256")
        != AUTHORITY_SHA256
    ):
        raise M2602ReleaseError("evaluation authority digest does not match the permitted dossier")
    scenarios = _integer(document.get("scenarioCount"), "evaluation.scenarioCount")
    passed = _integer(document.get("passed"), "evaluation.passed")
    if scenarios != EXPECTED_SCENARIOS or passed != scenarios:
        raise M2602ReleaseError("evaluation scenario matrix is incomplete")
    if not isinstance(document.get("scenarios"), dict):
        raise M2602ReleaseError("evaluation.scenarios must be an object")


def _check_benchmark(document: Mapping[str, object]) -> None:
    _check_identity(document, "benchmark")
    mean_ns = _integer(document.get("meanNs"), "benchmark.meanNs")
    p95_ns = _integer(document.get("p95Ns"), "benchmark.p95Ns")
    if mean_ns <= 0 or p95_ns <= 0 or mean_ns > MEAN_BUDGET_NS or p95_ns > P95_BUDGET_NS:
        raise M2602ReleaseError("benchmark exceeds the provisional latency budget")
    if document.get("passed") is not True:
        raise M2602ReleaseError("benchmark evidence is not marked passed")
    if _integer(document.get("sampleCount"), "benchmark.sampleCount") < MIN_BENCHMARK_SAMPLES:
        raise M2602ReleaseError("benchmark has fewer than ten measured samples")


def _check_coverage(document: Mapping[str, object]) -> None:
    _check_identity(document, "coverage")
    percent = _number(document.get("percentCovered"), "coverage.percentCovered")
    if percent < MIN_COVERAGE:
        raise M2602ReleaseError("branch-enabled coverage is below the release threshold")
    tests = _integer(document.get("testsPassed"), "coverage.testsPassed")
    statements = _integer(document.get("statements"), "coverage.statements")
    branches = _integer(document.get("branches"), "coverage.branches")
    if tests < 1 or statements < 1 or branches < 1:
        raise M2602ReleaseError("coverage evidence has invalid totals")


def _wheel_members(wheel: Path) -> tuple[str, ...]:
    try:
        with ZipFile(wheel) as archive:
            return tuple(archive.namelist())
    except (BadZipFile, OSError) as error:
        raise M2602ReleaseError("candidate wheel cannot be opened") from error


def _check_package(document: Mapping[str, object], wheel: Path, sdist: Path) -> None:
    _check_identity(document, "package")
    if _string(document.get("contractVersion"), "package.contractVersion") != CONTRACT_VERSION:
        raise M2602ReleaseError("package contract version is inconsistent")
    package_wheel = _mapping(document.get("wheel"), "package.wheel")
    package_sdist = _mapping(document.get("sdist"), "package.sdist")
    artifacts = (("wheel", wheel, package_wheel), ("sdist", sdist, package_sdist))
    for artifact, path, evidence in artifacts:
        if _string(evidence.get("filename"), f"package.{artifact}.filename") != path.name:
            raise M2602ReleaseError(f"package {artifact} filename does not match the supplied path")
        if _string(evidence.get("sha256"), f"package.{artifact}.sha256") != _sha256(path):
            raise M2602ReleaseError(f"package {artifact} digest does not match the supplied file")
        if (
            _integer(evidence.get("sizeBytes"), f"package.{artifact}.sizeBytes")
            != path.stat().st_size
        ):
            raise M2602ReleaseError(f"package {artifact} size does not match the supplied file")
    if document.get("isolatedImportPassed") is not True:
        raise M2602ReleaseError("isolated wheel import was not verified")
    if EXPECTED_WHEEL_MEMBER not in _wheel_members(wheel):
        raise M2602ReleaseError("wheel omits the M26-02 runtime module")


def verify(evidence_dir: Path, wheel: Path, sdist: Path) -> dict[str, object]:
    """Verify the evidence directory and candidate distributions."""

    evaluation = _json(evidence_dir / "evaluation.json")
    benchmark = _json(evidence_dir / "benchmark.json")
    coverage = _json(evidence_dir / "coverage.json")
    package = _json(evidence_dir / "package.json")
    _check_evaluation(evaluation)
    _check_benchmark(benchmark)
    _check_coverage(coverage)
    _check_package(package, wheel, sdist)
    return {
        "moduleId": MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "status": "passed",
        "checks": ["evaluation", "benchmark", "coverage", "package", "wheel-members"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.evidence_dir, args.wheel, args.sdist)
    except M2602ReleaseError as error:
        print(json.dumps({"moduleId": MODULE_ID, "status": "failed", "error": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
