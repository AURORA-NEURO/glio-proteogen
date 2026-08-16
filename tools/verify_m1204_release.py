"""Verify M12-04 executable and package release evidence."""

# Release verifier errors intentionally preserve useful diagnostics.
# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-04"
ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m12_04"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m12_04" / "scenarios.json"
FIXTURE_DIGEST: Final = "sha256:0613edb1881a8364c803756b7eac97c48120cebd71514f59b59a13b414292dd5"
CASE_IDS: Final = (
    "posterior_inference",
    "state_inference",
    "explicit_abstention",
    "unknown_method_abstention",
    "invalid_bounds_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


class M1204ReleaseVerificationError(ValueError):
    """Release evidence is incomplete or inconsistent."""


def _read(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M1204ReleaseVerificationError(f"{name} must contain an object")
    return cast("dict[str, Any]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_evaluation(value: dict[str, Any]) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual_ids = tuple(item["case_id"] for item in fixture["cases"])
    if value.get("module_id") != MODULE_ID or value.get("fixture_sha256") != FIXTURE_DIGEST:
        raise M1204ReleaseVerificationError("evaluation module or fixture digest mismatch")
    if actual_ids != CASE_IDS or tuple(value.get("case_ids", ())) != CASE_IDS:
        raise M1204ReleaseVerificationError("evaluation case IDs mismatch")
    if not (
        value.get("declared_cases") == 7
        and value.get("executed_cases") == 7
        and value.get("passed_cases") == 7
        and value.get("passed") is True
    ):
        raise M1204ReleaseVerificationError("evaluation is not a complete pass")


def _verify_benchmark(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("iterations", 0) < 1:
        raise M1204ReleaseVerificationError("benchmark identity or iteration count invalid")
    if not (
        value.get("mean_ns", 0) <= value.get("mean_budget_ns", 0)
        and value.get("p95_ns", 0) <= value.get("p95_budget_ns", 0)
        and value.get("passed") is True
    ):
        raise M1204ReleaseVerificationError("benchmark exceeds declared provisional budget")


def _verify_package(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("passed") is not True:
        raise M1204ReleaseVerificationError("package evidence identity or pass flag invalid")
    for kind in ("wheel", "sdist"):
        package = cast("dict[str, Any]", value.get(kind, {}))
        path = next((ROOT / "dist-m12-04").glob(str(package.get("filename", ""))), None)
        if path is None or not path.is_file():
            raise M1204ReleaseVerificationError(f"missing {kind} artifact")
        if _sha256(path) != package.get("sha256") or path.stat().st_size != package.get("bytes"):
            raise M1204ReleaseVerificationError(f"{kind} hash or size mismatch")
        if kind == "wheel":
            with zipfile.ZipFile(path) as archive:
                members = len(archive.namelist())
        else:
            with tarfile.open(path, "r:gz") as archive:
                members = len(archive.getnames())
        if members != package.get("members"):
            raise M1204ReleaseVerificationError(f"{kind} member count mismatch")
    isolated = cast("dict[str, Any]", value.get("isolated_import", {}))
    if isolated.get("passed") is not True:
        raise M1204ReleaseVerificationError("isolated import check did not pass")


def verify_release() -> dict[str, object]:
    """Verify all release-evidence records against current source/artifacts."""

    _verify_evaluation(_read("evaluation.json"))
    _verify_benchmark(_read("benchmark.json"))
    coverage = _read("coverage.json")
    if coverage.get("coverage_percent", 0) < coverage.get("fail_under_percent", 95):
        raise M1204ReleaseVerificationError("coverage evidence is below fail-under")
    if coverage.get("covered_statements") != coverage.get("statements") or coverage.get(
        "covered_branches"
    ) != coverage.get("branches"):
        raise M1204ReleaseVerificationError("coverage evidence is not complete")
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
    print("M12-04 release evidence verified")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
