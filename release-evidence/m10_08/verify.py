"""Machine-checkable M10-08 release evidence verifier."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tarfile
import zipfile
from typing import Any

_ROOT = pathlib.Path(__file__).parent
_GENERATED_MARKERS = (".coverage", "coverage_", "coverage.xml", "__pycache__", ".pyc")


def _load(name: str) -> dict[str, Any]:
    with (_ROOT / name).open(encoding="utf-8") as handle:
        return json.load(handle)  # type: ignore[no-any-return]


def _artifact_members(path: pathlib.Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, mode="r:gz") as archive:
        return archive.getnames()


def _check_package(package: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for artifact in package["artifacts"]:
        path = pathlib.Path(".m10-08-release-artifacts") / artifact["name"]
        if not path.exists():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            failures.append(f"hash:{artifact['name']}")
        members = _artifact_members(path)
        generated = [
            name for name in members if any(marker in name for marker in _GENERATED_MARKERS)
        ]
        if len(members) != artifact["members"] or generated or artifact["generated_members"] != 0:
            failures.append(f"members:{artifact['name']}")
        if artifact["unsafe_paths"] != 0:
            failures.append(f"paths:{artifact['name']}")
    return failures


def verify() -> dict[str, bool]:
    """Verify committed evaluator, benchmark, coverage, and package tuples."""

    coverage = _load("coverage.json")
    evaluation = _load("evaluation.json")
    benchmark = _load("benchmark.json")
    package = _load("package.json")
    coverage_ok = bool(
        coverage["passed"]
        and coverage["percent_covered"] >= coverage["fail_under"]
        and coverage["statements"]["covered"] + coverage["statements"]["missing"]
        == coverage["statements"]["total"]
        and coverage["branches"]["covered"] + coverage["branches"]["missing"]
        == coverage["branches"]["total"]
    )
    benchmark_ok = bool(
        benchmark["passed"]
        and benchmark["mean_ns"] <= benchmark["mean_budget_ns"]
        and benchmark["p95_ns"] <= benchmark["p95_budget_ns"]
    )
    result = {
        "coverage": coverage_ok,
        "evaluation": bool(evaluation["passed"]),
        "benchmark": benchmark_ok,
        "package": not _check_package(package),
    }
    if not all(result.values()):
        raise SystemExit from None
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))  # noqa: T201
