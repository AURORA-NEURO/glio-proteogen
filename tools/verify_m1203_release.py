"""Verify M12-03 evaluator, benchmark, coverage, and package evidence."""

# The verifier's stable failure messages are intentionally authored at call sites.
# ruff: noqa: TRY003, PLR2004

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-03"
DEFAULT_ROOT: Final = Path("release-evidence/m12_03")


class M1203ReleaseVerificationError(RuntimeError):
    """Raised when release evidence is incomplete or inconsistent."""


def _read(root: Path, name: str) -> dict[str, object]:
    return cast("dict[str, object]", json.loads((root / name).read_text(encoding="utf-8")))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_evaluation(root: Path) -> None:
    report = _read(root, "evaluation.json")
    if report.get("module_id") != MODULE_ID or report.get("passed") is not True:
        raise M1203ReleaseVerificationError("evaluation report is not passing")
    if report.get("declared_cases") != 6 or report.get("executed_cases") != 6:
        raise M1203ReleaseVerificationError("evaluation case count is not locked to six")
    coverage = cast("dict[str, object]", report.get("coverage", {}))
    if float(cast("float | int", coverage.get("branch_percent", 0))) < 95.0:
        raise M1203ReleaseVerificationError("coverage is below the release gate")
    if coverage.get("fail_under") != 95.0:
        raise M1203ReleaseVerificationError("coverage fail-under is not 95 percent")


def _verify_benchmark(root: Path) -> None:
    report = _read(root, "benchmark.json")
    if report.get("module_id") != MODULE_ID or report.get("passed") is not True:
        raise M1203ReleaseVerificationError("benchmark report is not passing")
    if int(cast("int", report.get("iterations", 0))) < 10:
        raise M1203ReleaseVerificationError("benchmark has fewer than ten iterations")
    if int(cast("int", report["mean_ns"])) > int(cast("int", report["mean_budget_ns"])):
        raise M1203ReleaseVerificationError("benchmark mean exceeds budget")
    if int(cast("int", report["p95_ns"])) > int(cast("int", report["p95_budget_ns"])):
        raise M1203ReleaseVerificationError("benchmark p95 exceeds budget")


def _member_count(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, mode="r:gz") as archive:
        return len(archive.getmembers())


def _verify_package(root: Path) -> None:
    report = _read(root, "package.json")
    if report.get("module_id") != MODULE_ID or report.get("isolated_import") is not True:
        raise M1203ReleaseVerificationError("package report is incomplete")
    for key in ("wheel", "sdist"):
        item = cast("dict[str, object]", report.get(key, {}))
        filename = str(item.get("filename", "pending"))
        path = root / filename
        if not path.exists() or item.get("sha256") != _digest(path):
            raise M1203ReleaseVerificationError(f"{key} hash does not match artifact")
        if int(cast("int", item.get("members", 0))) != _member_count(path):
            raise M1203ReleaseVerificationError(f"{key} member count does not match artifact")


def verify_release(root: Path = DEFAULT_ROOT) -> dict[str, object]:
    """Verify all evidence and return a concise passing summary."""

    _verify_evaluation(root)
    _verify_benchmark(root)
    _verify_package(root)
    return {"module_id": MODULE_ID, "verified": True, "root": str(root)}


def main() -> int:
    try:
        result = verify_release()
    except M1203ReleaseVerificationError as exc:
        print(json.dumps({"module_id": MODULE_ID, "verified": False, "error": str(exc)}))  # noqa: T201
        return 1
    print(json.dumps(result, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
