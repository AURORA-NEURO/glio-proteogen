# ruff: noqa: C901, PLR2004, T201, TRY003
"""Verify the locked, research-only proteomics evaluator and package surface.

This verifier deliberately checks computation identity and package reachability,
not scientific validity.  It reruns the six locked scenarios, binds the fixture
digest and scenario IDs, and optionally checks that built distributions contain
the research pipeline without requiring or implying a governed ABI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE = _ROOT / "docs" / "evidence" / "research-foundation"
_EXPECTED_SCENARIOS = (
    "target_supported",
    "decoy_rejected",
    "no_match",
    "precursor_rejected",
    "shared_peptide_group",
    "multi_spectrum",
)
_RESEARCH_MEMBERS = (
    "glio_proteogen/research/pipeline.py",
    "glio_proteogen/research/search.py",
    "glio_proteogen/research/protein.py",
)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.research_proteomics.run import run_benchmark, run_evaluator  # noqa: E402


class VerificationError(ValueError):
    """Raised when research evaluator or package evidence is inconsistent."""


def _read_json(path: Path) -> dict[str, object]:
    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid JSON evidence: {path}") from error
    if not isinstance(value, dict):
        raise VerificationError(f"evidence must be a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_evaluation(path: Path) -> None:
    evidence = _read_json(path)
    observed = run_evaluator()
    benchmark = run_benchmark(iterations=10)
    recorded_eval = evidence.get("evaluation") or evidence.get("evaluator")
    recorded_benchmark = evidence.get("benchmark")
    if not isinstance(recorded_eval, dict) or not isinstance(recorded_benchmark, dict):
        raise VerificationError("research evaluation must contain evaluation and benchmark")
    outcomes = observed.get("outcomes")
    if not isinstance(outcomes, list):
        raise VerificationError("research evaluator returned no outcomes")
    scenario_ids = tuple(item.get("scenario_id") for item in outcomes if isinstance(item, dict))
    if scenario_ids != _EXPECTED_SCENARIOS:
        raise VerificationError(f"unexpected research scenario IDs: {scenario_ids!r}")
    if observed.get("declared") != 6 or observed.get("executed") != 6 or not observed.get("passed"):
        raise VerificationError("research evaluator did not pass all six scenarios")
    recorded_fixture = evidence.get("fixture_sha256", recorded_eval.get("fixture_sha256"))
    if recorded_fixture != observed.get("fixture_sha256"):
        raise VerificationError("research fixture digest does not match the evaluator")
    recorded_scenarios = recorded_eval.get("scenario_ids", scenario_ids)
    if tuple(recorded_scenarios) != _EXPECTED_SCENARIOS:
        raise VerificationError("research evidence scenario inventory is not locked")
    if (
        recorded_eval.get("declared") != 6
        or recorded_eval.get("executed") != 6
        or not recorded_eval.get("passed")
    ):
        raise VerificationError("research evaluation evidence is not passing")
    if recorded_benchmark.get("result_digest") != benchmark.get("result_digest"):
        raise VerificationError("research benchmark result digest changed")
    iterations = recorded_benchmark.get("iterations")
    if iterations != 10:
        raise VerificationError("research benchmark must contain exactly ten timed iterations")
    for key in ("mean_ns", "median_ns", "p95_ns"):
        value = recorded_benchmark.get(key)
        if not isinstance(value, (int, float)) or value <= 0:
            raise VerificationError(f"research benchmark field {key} is invalid")
    coverage = evidence.get("coverage")
    if coverage is not None and (
        not isinstance(coverage, dict)
        or float(coverage.get("percent", 0.0)) < float(coverage.get("fail_under", 95.0))
    ):
        raise VerificationError("research coverage evidence is below its fail-under threshold")


def _verify_package(path: Path) -> None:
    if not path.is_file():
        raise VerificationError(f"package does not exist: {path}")
    if path.name.endswith(".whl"):
        with ZipFile(path) as archive:
            names = set(archive.namelist())
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = set(archive.getnames())
    else:
        raise VerificationError("package must be a wheel or sdist")
    for member in _RESEARCH_MEMBERS:
        if not any(name.endswith(member) for name in names):
            raise VerificationError(f"package omits research member {member}")


def verify(evaluation: Path, wheel: Path | None = None, sdist: Path | None = None) -> None:
    """Verify evaluator evidence and, when supplied, package reachability."""

    _verify_evaluation(evaluation)
    if (wheel is None) != (sdist is None):
        raise VerificationError("wheel and sdist must be supplied together")
    if wheel is not None and sdist is not None:
        _verify_package(wheel)
        _verify_package(sdist)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("wheel", type=Path, nargs="?")
    parser.add_argument("sdist", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        verify(args.evaluation, args.wheel, args.sdist)
    except (OSError, KeyError, TypeError, ValueError, tarfile.TarError) as error:
        print(f"research pipeline verification failed: {error}", file=sys.stderr)
        return 1
    print("research pipeline verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
