"""Verify the M14-06 executable and package release evidence."""

# Release verifier errors intentionally preserve a useful diagnostic and the
# fixture cardinality is a locked protocol value.
# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M14-06"
ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m14_06"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m14_06" / "scenarios.json"
FIXTURE_DIGEST: Final = "sha256:e97fcae295436951747bcb0d558ca13098e5173ccc83c1dc7a4a0a39b2cac0af"
CASE_IDS: Final = (
    "bounded_simulation",
    "alternative_prior",
    "assay_perturbation",
    "unsupported_model_abstention",
    "missing_value_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


class M1406ReleaseVerificationError(ValueError):
    """Release evidence is incomplete or inconsistent."""


def _read(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M1406ReleaseVerificationError(f"{name} must contain an object")
    return cast("dict[str, Any]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_evaluation(value: dict[str, Any]) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual_ids = tuple(item["case_id"] for item in fixture["cases"])
    if value.get("module_id") != MODULE_ID or value.get("fixture_sha256") != FIXTURE_DIGEST:
        raise M1406ReleaseVerificationError("evaluation module or fixture digest mismatch")
    if actual_ids != CASE_IDS or tuple(value.get("case_ids", ())) != CASE_IDS:
        raise M1406ReleaseVerificationError("evaluation case IDs mismatch")
    if not (
        value.get("declared_cases") == 7
        and value.get("executed_cases") == 7
        and value.get("passed_cases") == 7
        and value.get("passed") is True
    ):
        raise M1406ReleaseVerificationError("evaluation is not a complete pass")


def _verify_benchmark(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("iterations", 0) < 1:
        raise M1406ReleaseVerificationError("benchmark identity or iteration count invalid")
    if not (
        value.get("mean_ns", 0) <= value.get("mean_budget_ns", 0)
        and value.get("p95_ns", 0) <= value.get("p95_budget_ns", 0)
        and value.get("passed") is True
    ):
        raise M1406ReleaseVerificationError("benchmark exceeds declared provisional budget")


def _verify_package(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("passed") is not True:
        raise M1406ReleaseVerificationError("package evidence identity or pass flag invalid")
    for kind in ("wheel", "sdist"):
        package = cast("dict[str, Any]", value.get(kind, {}))
        path = next((ROOT / "dist-m14-06").glob(str(package.get("filename", ""))), None)
        if path is None or not path.is_file():
            raise M1406ReleaseVerificationError(f"missing {kind} artifact")
        if _sha256(path) != package.get("sha256") or path.stat().st_size != package.get("bytes"):
            raise M1406ReleaseVerificationError(f"{kind} hash or size mismatch")
        if kind == "wheel":
            with zipfile.ZipFile(path) as archive:
                members = len(archive.namelist())
        else:
            with tarfile.open(path, "r:gz") as archive:
                members = len(archive.getnames())
        if members != package.get("members"):
            raise M1406ReleaseVerificationError(f"{kind} member count mismatch")
    isolated = cast("dict[str, Any]", value.get("isolated_import", {}))
    if isolated.get("passed") is not True:
        raise M1406ReleaseVerificationError("isolated import check did not pass")


def verify_release() -> dict[str, object]:
    """Verify all release-evidence records against current source/artifacts."""

    _verify_evaluation(_read("evaluation.json"))
    _verify_benchmark(_read("benchmark.json"))
    coverage = _read("coverage.json")
    if coverage.get("coverage_percent", 0) < coverage.get("fail_under_percent", 95):
        raise M1406ReleaseVerificationError("coverage evidence is below fail-under")
    _verify_package(_read("package.json"))
    return {
        "module_id": MODULE_ID,
        "evaluation": True,
        "benchmark": True,
        "coverage": True,
        "package": True,
    }


def main() -> int:
    verify_release()
    print("M14-06 release evidence verified")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

