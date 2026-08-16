"""Verify M12-08 executable, coverage, and package release evidence."""

# Release verifier errors intentionally preserve useful diagnostics.
# ruff: noqa: PLR2004, TRY003, T201

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-08"
ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m12_08"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m12_08" / "scenarios.json"
DIST: Final = ROOT / "dist-m12-08"
FIXTURE_DIGEST: Final = "sha256:f28607d12df051e209634727812000120b3f6c1e2f9c2a1609a457ee7dd3d7f7"
CASE_IDS: Final = (
    "bayesian_graph_dossier",
    "network_factor_dossier",
    "curated_rule_dossier",
    "orthogonal_consensus_dossier",
    "unsupported_architecture_abstention",
    "unsafe_upstream_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


class M1208ReleaseVerificationError(ValueError):
    """Release evidence is incomplete or inconsistent."""


def _read(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M1208ReleaseVerificationError(f"{name} must contain an object")
    return cast("dict[str, Any]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_evaluation(value: dict[str, Any]) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual_ids = tuple(item["case_id"] for item in fixture["cases"])
    if value.get("module_id") != MODULE_ID or value.get("fixture_sha256") != FIXTURE_DIGEST:
        raise M1208ReleaseVerificationError("evaluation module or fixture digest mismatch")
    if actual_ids != CASE_IDS or tuple(value.get("case_ids", ())) != CASE_IDS:
        raise M1208ReleaseVerificationError("evaluation case IDs mismatch")
    if not (
        value.get("declared_cases") == 8
        and value.get("executed_cases") == 8
        and value.get("passed_cases") == 8
        and value.get("passed") is True
    ):
        raise M1208ReleaseVerificationError("evaluation is not a complete pass")


def _verify_benchmark(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("iterations", 0) < 1:
        raise M1208ReleaseVerificationError("benchmark identity or iteration count invalid")
    if not (
        value.get("mean_ns", 0) <= value.get("mean_budget_ns", 0)
        and value.get("p95_ns", 0) <= value.get("p95_budget_ns", 0)
        and value.get("passed") is True
    ):
        raise M1208ReleaseVerificationError("benchmark exceeds declared provisional budget")


def _verify_package(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("passed") is not True:
        raise M1208ReleaseVerificationError("package evidence identity or pass flag invalid")
    for kind in ("wheel", "sdist"):
        package = cast("dict[str, Any]", value.get(kind, {}))
        filename = package.get("filename")
        path = DIST / str(filename)
        if not filename or not path.is_file():
            raise M1208ReleaseVerificationError(f"missing {kind} artifact")
        if _sha256(path) != package.get("sha256") or path.stat().st_size != package.get("bytes"):
            raise M1208ReleaseVerificationError(f"{kind} hash or size mismatch")
        if kind == "wheel":
            with zipfile.ZipFile(path) as archive:
                members = len(archive.namelist())
        else:
            with tarfile.open(path, "r:gz") as archive:
                members = len(archive.getnames())
        if members != package.get("members") or members < 1:
            raise M1208ReleaseVerificationError(f"{kind} member count mismatch")
    isolated = cast("dict[str, Any]", value.get("isolated_import", {}))
    if isolated.get("passed") is not True:
        raise M1208ReleaseVerificationError("isolated import check did not pass")


def verify_release() -> dict[str, object]:
    """Verify all M12-08 release-evidence records against current artifacts."""

    _verify_evaluation(_read("evaluation.json"))
    _verify_benchmark(_read("benchmark.json"))
    coverage = _read("coverage.json")
    if coverage.get("coverage_percent", 0) < coverage.get("fail_under_percent", 95):
        raise M1208ReleaseVerificationError("coverage evidence is below fail-under")
    if not (
        isinstance(coverage.get("statements"), int)
        and isinstance(coverage.get("covered_statements"), int)
        and isinstance(coverage.get("branches"), int)
        and isinstance(coverage.get("covered_branches"), int)
        and 0 <= coverage["covered_statements"] <= coverage["statements"]
        and 0 <= coverage["covered_branches"] <= coverage["branches"]
    ):
        raise M1208ReleaseVerificationError("coverage evidence counts are invalid")
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
    print("M12-08 release evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
