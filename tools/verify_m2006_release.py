"""Verify the M20-06 release-evidence manifests and package records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MODULE = "GLIO-PROTEOGEN-M20-06"
AUTHORITY = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:7096-7136"
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
MIN_COVERAGE = 95.0
SCENARIO_COUNT = 9
BENCHMARK_ITERATIONS = 25


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")  # noqa: TRY003
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path, wheel: Path | None = None, sdist: Path | None = None) -> dict[str, object]:
    evidence = root / "release-evidence" / "m20_06"
    evaluation = _load(evidence / "evaluation.json")
    benchmark = _load(evidence / "benchmark.json")
    coverage = _load(evidence / "coverage.json")
    checks: dict[str, bool] = {
        "module": evaluation.get("module_id")
        == MODULE
        == benchmark.get("module_id")
        == coverage.get("module_id"),
        "authority": evaluation.get("dossier_sha256") == AUTHORITY
        and evaluation.get("dossier_slice") == SLICE,
        "evaluation": evaluation.get("passed") is True
        and evaluation.get("scenario_count") == SCENARIO_COUNT
        and evaluation.get("adversarial_passed_count") == evaluation.get("adversarial_case_count"),
        "benchmark": benchmark.get("passed") is True
        and benchmark.get("iterations") == BENCHMARK_ITERATIONS
        and benchmark.get("mean_ns", MEAN_BUDGET_NS + 1) <= MEAN_BUDGET_NS
        and benchmark.get("p95_ns", P95_BUDGET_NS + 1) <= P95_BUDGET_NS,
        "coverage": coverage.get("branch_enabled") is True
        and coverage.get("coverage_percent", 0) >= MIN_COVERAGE
        and coverage.get("passed") is True,
    }
    if wheel is not None and sdist is not None:
        package = _load(evidence / "package.json")
        wheel_record = package.get("wheel")
        sdist_record = package.get("sdist")
        checks["package"] = (
            package.get("module_id") == MODULE
            and package.get("passed") is True
            and isinstance(wheel_record, dict)
            and isinstance(sdist_record, dict)
            and wheel.name == wheel_record.get("filename")
            and sdist.name == sdist_record.get("filename")
            and wheel.stat().st_size == wheel_record.get("size_bytes")
            and _sha256(wheel) == wheel_record.get("sha256")
            and sdist.stat().st_size == sdist_record.get("size_bytes")
            and _sha256(sdist) == sdist_record.get("sha256")
            and package.get("isolated_import") is True
        )
        if checks["package"]:
            try:
                with ZipFile(wheel) as archive:
                    checks["wheel_members"] = len(archive.namelist()) == wheel_record.get(
                        "member_count"
                    )
            except (BadZipFile, OSError):
                checks["wheel_members"] = False
    return {"module_id": MODULE, "checks": checks, "passed": all(checks.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args(argv)
    report = verify(args.root, args.wheel, args.sdist)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
