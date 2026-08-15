"""Verify machine-readable M12-06 evaluation, benchmark, and package evidence."""

# This verifier intentionally reports concise CLI diagnostics and uses explicit
# evidence-field messages.
# ruff: noqa: TRY003,PLR2004,T201

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-06"
ROOT: Final = Path(__file__).resolve().parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m12_06"
EXPECTED_CASE_IDS: Final = (
    "supported_bounded_surface",
    "unsupported_perturbation_abstains",
    "out_of_envelope_abstains",
    "consent_denied",
    "identity_denied",
    "support_denied",
)


class M1206ReleaseVerificationError(RuntimeError):
    """Evidence is incomplete, stale, or contradicts the module contract."""


def _load(name: str) -> dict[str, object]:
    path = EVIDENCE / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M1206ReleaseVerificationError(f"cannot read {name}") from error
    if not isinstance(value, dict):
        raise M1206ReleaseVerificationError(f"{name} must contain an object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_evaluation(value: dict[str, object]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("passed") is not True:
        raise M1206ReleaseVerificationError("evaluation module or status mismatch")
    declared = value.get("declared_case_ids")
    executed = value.get("executed_case_ids")
    if not isinstance(declared, list) or not isinstance(executed, list):
        raise M1206ReleaseVerificationError("evaluation case manifest mismatch")
    if not all(isinstance(item, str) for item in (*declared, *executed)):
        raise M1206ReleaseVerificationError("evaluation case manifest mismatch")
    if tuple(declared) != EXPECTED_CASE_IDS or tuple(executed) != EXPECTED_CASE_IDS:
        raise M1206ReleaseVerificationError("evaluation case manifest mismatch")
    coverage = value.get("coverage")
    if (
        not isinstance(coverage, dict)
        or float(cast("float", coverage.get("total_percent", 0))) < 95.0
    ):
        raise M1206ReleaseVerificationError("scoped branch coverage is below 95 percent")
    checks = value.get("checks")
    if not isinstance(checks, list) or not all(
        isinstance(item, dict) and item.get("passed") is True for item in checks
    ):
        raise M1206ReleaseVerificationError("evaluation checks are not all passing")


def _verify_benchmark(value: dict[str, object]) -> None:
    if value.get("module_id") != MODULE_ID or value.get("passed") is not True:
        raise M1206ReleaseVerificationError("benchmark module or status mismatch")
    if int(cast("int", value.get("iterations", 0))) != 10:
        raise M1206ReleaseVerificationError("benchmark must contain ten timed iterations")
    if float(cast("float", value.get("mean_ns", 0))) > int(
        cast("int", value.get("mean_budget_ns", 0))
    ):
        raise M1206ReleaseVerificationError("benchmark mean exceeds budget")
    if int(cast("int", value.get("p95_ns", 0))) > int(cast("int", value.get("p95_budget_ns", 0))):
        raise M1206ReleaseVerificationError("benchmark p95 exceeds budget")


def _archive_member_count(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return len(archive.getnames())


def _verify_package(value: dict[str, object]) -> None:
    wheel = ROOT / cast("str", value.get("wheel_path", ""))
    sdist = ROOT / cast("str", value.get("sdist_path", ""))
    if not wheel.is_file() or not sdist.is_file():
        raise M1206ReleaseVerificationError("package artifacts are missing")
    if _sha256(wheel) != value.get("wheel_sha256") or _sha256(sdist) != value.get("sdist_sha256"):
        raise M1206ReleaseVerificationError("package hash mismatch")
    if _archive_member_count(wheel) != int(cast("int", value.get("wheel_members", -1))):
        raise M1206ReleaseVerificationError("wheel member count mismatch")
    if _archive_member_count(sdist) != int(cast("int", value.get("sdist_members", -1))):
        raise M1206ReleaseVerificationError("sdist member count mismatch")
    if value.get("isolated_import") is not True:
        raise M1206ReleaseVerificationError("isolated import gate is not recorded")


def verify_release() -> dict[str, object]:
    """Verify all M12-06 release evidence and return a compact report."""

    _verify_evaluation(_load("evaluation.json"))
    _verify_benchmark(_load("benchmark.json"))
    _verify_package(_load("package.json"))
    return {"module_id": MODULE_ID, "passed": True}


def main() -> int:
    try:
        report = verify_release()
    except M1206ReleaseVerificationError as error:
        print(f"M12-06 release verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
