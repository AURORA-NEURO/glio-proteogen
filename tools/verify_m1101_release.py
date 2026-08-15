"""Verify fixture-bound M11-01 release evidence and package metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

EXPECTED_CASE_IDS: Final = (
    "supported_registry",
    "refuted_hypothesis",
    "unknown_hypothesis",
    "failed_falsification",
    "unknown_falsification",
    "multiple_supported",
    "denied_control",
)
MODULE_ID: Final = "GLIO-PROTEOGEN-M11-01"
FIXTURE_DIGEST: Final = "sha256:823c21c3868e5f1a769fc0a6e7836a00055c6fa2d0f8b815c0fd88745af0c4d4"
MIN_COVERAGE_PERCENT: Final = 95.0


class M1101ReleaseVerificationError(ValueError):
    """M11-01 release evidence is not internally locked."""

    def __init__(self) -> None:
        super().__init__("M11-01 release evidence verification failed")


def verify_release(root: Path) -> dict[str, object]:
    evaluation = json.loads((root / "evaluation.json").read_text(encoding="utf-8"))
    benchmark = json.loads((root / "benchmark.json").read_text(encoding="utf-8"))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if evaluation["module_id"] != MODULE_ID or evaluation["fixture_digest"] != FIXTURE_DIGEST:
        raise M1101ReleaseVerificationError
    if tuple(evaluation["case_ids"]) != EXPECTED_CASE_IDS:
        raise M1101ReleaseVerificationError
    if (
        evaluation["declared"] != len(EXPECTED_CASE_IDS)
        or evaluation["executed"] != len(EXPECTED_CASE_IDS)
        or not evaluation["passed"]
        or evaluation["failed"]
    ):
        raise M1101ReleaseVerificationError
    if benchmark["module_id"] != MODULE_ID or not benchmark["deterministic"]:
        raise M1101ReleaseVerificationError
    if benchmark["mean_ns"] > benchmark["mean_budget_ns"]:
        raise M1101ReleaseVerificationError
    if benchmark["p95_ns"] > benchmark["p95_budget_ns"]:
        raise M1101ReleaseVerificationError
    if float(package["coverage_percent"]) < MIN_COVERAGE_PERCENT:
        raise M1101ReleaseVerificationError
    for key in ("wheel_sha256", "sdist_sha256", "wheel_members", "sdist_members"):
        if key not in package:
            raise M1101ReleaseVerificationError
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
        sys.stderr.write("usage: verify_m1101_release.py RELEASE_EVIDENCE_DIR\n")
        return 2
    try:
        sys.stdout.write(json.dumps(verify_release(Path(args[0])), sort_keys=True) + "\n")
    except (OSError, KeyError, TypeError, M1101ReleaseVerificationError) as error:
        sys.stderr.write(f"M11-01 release verification failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
