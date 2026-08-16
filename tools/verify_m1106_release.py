"""Verify M11-06 evaluator, benchmark, and package evidence."""

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final, NoReturn

MODULE_ID: Final = "GLIO-PROTEOGEN-M11-06"
FIXTURE_DIGEST: Final = "sha256:63b91844d2890d0aa9916b7f46a053f6bb7b3bf93887f81e117b3572d02eec30"
EXPECTED_CASES: Final = (
    "supported_in_silico",
    "parameter_sweep",
    "alternative_prior",
    "assay_perturbation",
    "mechanism_stress",
    "unsupported_ood",
    "prohibited_ownership",
    "missing_negative_control",
    "denied_control",
)
MIN_BRANCH_COVERAGE: Final = 95.0
MIN_BENCHMARK_ITERATIONS: Final = 10


class M1106ReleaseVerificationError(ValueError):
    """Release evidence does not satisfy the M11-06 closure."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"M11-06 release verification failed: {reason}")


def _reject(reason: str) -> NoReturn:
    raise M1106ReleaseVerificationError(reason)


def _read(root: Path, relative: str) -> dict[str, Any]:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        _reject("evidence path escapes repository root")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise M1106ReleaseVerificationError(f"cannot read {relative}") from error  # noqa: TRY003
    if not isinstance(document, dict):
        _reject(f"{relative} is not a JSON object")
    return document


def _verify_evaluation(root: Path) -> dict[str, Any]:
    document = _read(root, "release-evidence/m11_06/evaluation.json")
    if document.get("module_id") != MODULE_ID:
        _reject("evaluation module id mismatch")
    if document.get("fixture_digest") != FIXTURE_DIGEST:
        _reject("fixture digest mismatch")
    if document.get("passed") is not True:
        _reject("evaluator did not pass")
    outcomes = document.get("outcomes")
    if not isinstance(outcomes, list):
        _reject("evaluation outcomes are not a list")
    actual_cases = tuple(str(item.get("case_id")) for item in outcomes if isinstance(item, dict))
    if actual_cases != EXPECTED_CASES:
        _reject("evaluation case catalogue mismatch")
    if document.get("declared") != len(EXPECTED_CASES) or document.get("executed") != len(
        EXPECTED_CASES
    ):
        _reject("evaluation counts mismatch")
    if any(
        not isinstance(item, dict) or item.get("expected") != item.get("actual")
        for item in outcomes
    ):
        _reject("evaluation contains a failed case")
    coverage = document.get("coverage")
    if not isinstance(coverage, dict) or float(coverage.get("branch_coverage", 0.0)) < (
        MIN_BRANCH_COVERAGE
    ):
        _reject("branch coverage is below the release gate")
    return document


def _verify_benchmark(root: Path) -> dict[str, Any]:
    document = _read(root, "release-evidence/m11_06/benchmark.json")
    if document.get("module_id") != MODULE_ID or document.get("passed") is not True:
        _reject("benchmark did not pass")
    if int(document.get("iterations", 0)) < MIN_BENCHMARK_ITERATIONS:
        _reject("benchmark iteration count is too small")
    if int(document["mean_ns"]) > int(document["mean_budget_ns"]):
        _reject("benchmark mean budget exceeded")
    if int(document["p95_ns"]) > int(document["p95_budget_ns"]):
        _reject("benchmark p95 budget exceeded")
    return document


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _member_count(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return len(archive.getnames())


def _verify_package(root: Path) -> dict[str, Any]:
    document = _read(root, "release-evidence/m11_06/package.json")
    if document.get("module_id") != MODULE_ID or document.get("isolated_import") is not True:
        _reject("package evidence is incomplete")
    for key, suffix in (("wheel", ".whl"), ("sdist", ".tar.gz")):
        artifact = document.get(key)
        if not isinstance(artifact, dict):
            _reject(f"{key} evidence is missing")
        path = (root / str(artifact.get("filename", ""))).resolve()
        if root.resolve() not in path.parents or not path.name.endswith(suffix):
            _reject(f"invalid {key} path")
        if not path.is_file():
            _reject(f"{key} artifact is missing")
        if _digest(path) != artifact.get("sha256"):
            _reject(f"{key} digest mismatch")
        if path.stat().st_size != int(artifact.get("size_bytes", -1)):
            _reject(f"{key} size mismatch")
        if _member_count(path) != int(artifact.get("members", -1)):
            _reject(f"{key} member count mismatch")
    return document


def verify_release(root: Path) -> dict[str, Any]:
    """Verify all M11-06 release evidence under ``root``."""

    root = root.resolve()
    evaluation = _verify_evaluation(root)
    benchmark = _verify_benchmark(root)
    package = _verify_package(root)
    return {
        "module_id": MODULE_ID,
        "passed": True,
        "fixture_digest": evaluation["fixture_digest"],
        "benchmark_mean_ns": benchmark["mean_ns"],
        "benchmark_p95_ns": benchmark["p95_ns"],
        "wheel_sha256": package["wheel"]["sha256"],
        "sdist_sha256": package["sdist"]["sha256"],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify_release(root), sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
