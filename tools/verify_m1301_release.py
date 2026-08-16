"""Verify fixture-bound M13-01 release evidence and package metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final, cast

EXPECTED_CASE_IDS: Final = (
    "supported_registry",
    "refuted_hypothesis",
    "unknown_hypothesis",
    "failed_falsification",
    "unknown_falsification",
    "multiple_supported",
    "denied_control",
)
MODULE_ID: Final = "GLIO-PROTEOGEN-M13-01"
FIXTURE_DIGEST: Final = "sha256:823c21c3868e5f1a769fc0a6e7836a00055c6fa2d0f8b815c0fd88745af0c4d4"
MIN_COVERAGE_PERCENT: Final = 95.0


class M1301ReleaseVerificationError(ValueError):
    """M13-01 release evidence is not internally locked."""

    def __init__(self) -> None:
        super().__init__("M13-01 release evidence verification failed")


def _verify_evaluation(evaluation: dict[str, Any]) -> None:
    if evaluation["module_id"] != MODULE_ID or evaluation["fixture_digest"] != FIXTURE_DIGEST:
        raise M1301ReleaseVerificationError
    if tuple(evaluation["case_ids"]) != EXPECTED_CASE_IDS:
        raise M1301ReleaseVerificationError
    if (
        evaluation["declared"] != len(EXPECTED_CASE_IDS)
        or evaluation["executed"] != len(EXPECTED_CASE_IDS)
        or not evaluation["passed"]
        or evaluation["failed"]
    ):
        raise M1301ReleaseVerificationError


def _verify_benchmark(benchmark: dict[str, Any]) -> None:
    if benchmark["module_id"] != MODULE_ID or not benchmark["deterministic"]:
        raise M1301ReleaseVerificationError
    if benchmark["iterations"] < 1:
        raise M1301ReleaseVerificationError
    if benchmark["mean_ns"] > benchmark["mean_budget_ns"]:
        raise M1301ReleaseVerificationError
    if benchmark["p95_ns"] > benchmark["p95_budget_ns"]:
        raise M1301ReleaseVerificationError


def _verify_package(package: dict[str, Any]) -> None:
    if float(package["coverage_percent"]) < MIN_COVERAGE_PERCENT:
        raise M1301ReleaseVerificationError
    for key in ("wheel", "sdist"):
        artifact = package[key]
        if not artifact["filename"] or not artifact["sha256"]:
            raise M1301ReleaseVerificationError
        if int(artifact["members"]) <= 0 or int(artifact["size_bytes"]) <= 0:
            raise M1301ReleaseVerificationError
    if not package["isolated_import"]:
        raise M1301ReleaseVerificationError


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
        "coverage_percent": package["coverage_percent"],
        "package": "passed",
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: verify_m1301_release.py RELEASE_EVIDENCE_DIR\n")
        return 2
    try:
        sys.stdout.write(json.dumps(verify_release(Path(args[0])), sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, M1301ReleaseVerificationError) as error:
        sys.stderr.write(f"M13-01 release verification failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
