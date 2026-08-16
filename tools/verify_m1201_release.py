"""Verify fixture-bound M12-01 release evidence and package metadata."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-01"
CONTRACT_VERSION: Final = "0.1.0-provisional"
EXPECTED_CASE_IDS: Final = (
    "supported_registry",
    "refuted_hypothesis",
    "unknown_hypothesis",
    "failed_falsification",
    "unknown_falsification",
    "multiple_supported",
    "denied_control",
)
FIXTURE_DIGEST: Final = "sha256:823c21c3868e5f1a769fc0a6e7836a00055c6fa2d0f8b815c0fd88745af0c4d4"
MIN_COVERAGE_PERCENT: Final = 95.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class M1201ReleaseVerificationError(ValueError):
    """M12-01 release evidence is not internally locked."""

    def __init__(self) -> None:
        super().__init__("M12-01 release evidence verification failed")


def _verify_evaluation(evaluation: dict[str, Any]) -> None:
    if (
        evaluation.get("module_id") != MODULE_ID
        or evaluation.get("contract_version") != CONTRACT_VERSION
        or evaluation.get("fixture_sha256") != FIXTURE_DIGEST
    ):
        raise M1201ReleaseVerificationError
    cases = evaluation.get("cases")
    if (
        not isinstance(cases, list)
        or tuple(item.get("case_id") for item in cases) != EXPECTED_CASE_IDS
    ):
        raise M1201ReleaseVerificationError
    if (
        evaluation.get("declared") != len(EXPECTED_CASE_IDS)
        or evaluation.get("executed") != len(EXPECTED_CASE_IDS)
        or not evaluation.get("passed")
        or any(item.get("expected") != item.get("actual") for item in cases)
    ):
        raise M1201ReleaseVerificationError
    coverage = evaluation.get("coverage")
    if not isinstance(coverage, dict) or not coverage.get("branch_enabled"):
        raise M1201ReleaseVerificationError
    if float(coverage.get("percent", 0.0)) < MIN_COVERAGE_PERCENT:
        raise M1201ReleaseVerificationError


def _verify_benchmark(benchmark: dict[str, Any]) -> None:
    if benchmark.get("module_id") != MODULE_ID or not benchmark.get("deterministic"):
        raise M1201ReleaseVerificationError
    if (
        int(benchmark["mean_ns"]) > int(benchmark["mean_budget_ns"])
        or int(benchmark["p95_ns"]) > int(benchmark["p95_budget_ns"])
        or not benchmark.get("within_budget")
        or int(benchmark["iterations"]) < 1
    ):
        raise M1201ReleaseVerificationError


def _verify_package(package: dict[str, Any]) -> None:
    if package.get("module_id") != MODULE_ID or package.get("build_backend") != "hatchling":
        raise M1201ReleaseVerificationError
    for kind in ("wheel", "sdist"):
        artifact = package.get(kind)
        if not isinstance(artifact, dict):
            raise M1201ReleaseVerificationError
        digest = artifact.get("sha256", "")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise M1201ReleaseVerificationError
        if int(artifact.get("size_bytes", 0)) <= 0 or int(artifact.get("members", 0)) <= 0:
            raise M1201ReleaseVerificationError
    if not package.get("isolated_import"):
        raise M1201ReleaseVerificationError


def verify_release(root: Path) -> dict[str, object]:
    evaluation = cast(
        "dict[str, Any]", json.loads((root / "evaluation.json").read_text(encoding="utf-8"))
    )
    benchmark = cast(
        "dict[str, Any]", json.loads((root / "benchmark.json").read_text(encoding="utf-8"))
    )
    package = cast(
        "dict[str, Any]", json.loads((root / "package.json").read_text(encoding="utf-8"))
    )
    _verify_evaluation(evaluation)
    _verify_benchmark(benchmark)
    _verify_package(package)
    return {
        "module_id": MODULE_ID,
        "evaluation": "passed",
        "benchmark": "passed",
        "coverage_percent": evaluation["coverage"]["percent"],
        "package": "passed",
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: verify_m1201_release.py RELEASE_EVIDENCE_DIR\n")
        return 2
    try:
        sys.stdout.write(json.dumps(verify_release(Path(args[0])), sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, ValueError, M1201ReleaseVerificationError) as error:
        sys.stderr.write(f"M12-01 release verification failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
