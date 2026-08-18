# ruff: noqa: PLR2004, T201, TRY003
"""Verify the locked, research-only proteomics evaluator and package surface.

This verifier deliberately checks computation identity and package reachability,
not scientific validity. It reruns the eight single-run and nine cohort locked
scenarios, binds fixture digests and scenario IDs, and optionally checks that built
distributions contain
the research pipeline without requiring or implying a governed ABI.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
import tarfile
from pathlib import Path
from typing import cast
from zipfile import ZipFile

_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE = _ROOT / "docs" / "evidence" / "research-foundation"
_EXPECTED_SCENARIOS = (
    "target_supported",
    "decoy_rejected",
    "target_decoy_collision",
    "no_match",
    "precursor_rejected",
    "shared_peptide_group",
    "multi_spectrum",
    "multi_peptide_quantification",
)
_EXPECTED_COHORT_SCENARIOS = (
    "replicate_matrix",
    "qc_abstention",
    "explicit_missingness",
    "label_normalization",
    "duplicate_biological_source",
    "technical_duplicate_visibility",
    "unknown_independence_abstention",
    "incompatible_search_space",
    "pdc_provenance_replay",
)
_RESEARCH_MEMBERS = (
    "glio_proteogen/research/pipeline.py",
    "glio_proteogen/research/pdc.py",
    "glio_proteogen/research/public_proteomics/provenance.py",
    "glio_proteogen/research/search.py",
    "glio_proteogen/research/protein.py",
    "glio_proteogen/research/cohort.py",
    "glio_proteogen/research/cohort_provenance.py",
)
_EXPECTED_SOURCE_DATE_EPOCH = 315532800

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.research_proteomics.cohort import (  # noqa: E402
    run_evaluator as run_cohort_evaluator,
)
from evals.research_proteomics.precursor_policy import (  # noqa: E402
    run_precursor_policy_evaluator,
)
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


def _finite_positive_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    numeric = cast("int | float", value)
    return math.isfinite(numeric) and numeric > 0


def _verify_benchmark_record(recorded: dict[str, object]) -> None:
    """Validate recorded samples and recompute all reported statistics."""

    if recorded.get("iterations") != 10:
        raise VerificationError("research benchmark must contain exactly ten timed iterations")
    if recorded.get("percentile_method") != "nearest_rank":
        raise VerificationError("research benchmark percentile method is not locked")
    samples = recorded.get("samples_ns")
    if (
        not isinstance(samples, list)
        or len(samples) != 10
        or any(type(sample) is not int or sample <= 0 for sample in samples)
    ):
        raise VerificationError("research benchmark samples are incomplete or invalid")
    ordered = sorted(samples)
    expected_mean = sum(samples) / len(samples)
    expected_median = ordered[len(ordered) // 2]
    expected_p95 = ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]
    if not _finite_positive_number(recorded.get("mean_ns")):
        raise VerificationError("research benchmark field mean_ns is invalid")
    recorded_mean = cast("int | float", recorded["mean_ns"])
    if not math.isclose(recorded_mean, expected_mean, rel_tol=0.0, abs_tol=1e-9):
        raise VerificationError("research benchmark mean does not match samples")
    if recorded.get("median_ns") != expected_median:
        raise VerificationError("research benchmark median does not match samples")
    if recorded.get("p95_ns") != expected_p95:
        raise VerificationError("research benchmark p95 does not match samples")


def _require_installed_research_runtime() -> None:
    """Reject artifact-bound verification when the checkout shadows the wheel."""

    module = importlib.import_module("glio_proteogen.research")
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise VerificationError("installed research package has no import origin")
    origin_path = Path(origin).resolve()
    if origin_path.is_relative_to(_ROOT / "src"):
        raise VerificationError(
            "artifact-bound research verification must run from the installed wheel"
        )


def _verify_evaluation(path: Path) -> str:  # noqa: C901, PLR0912
    evidence = _read_json(path)
    observed = run_evaluator()
    benchmark = run_benchmark(iterations=10)
    recorded_eval = evidence.get("evaluation") or evidence.get("evaluator")
    recorded_cohort = evidence.get("cohort_evaluation")
    recorded_precursor_policy = evidence.get("precursor_policy_evaluation")
    recorded_benchmark = evidence.get("benchmark")
    if (
        not isinstance(recorded_eval, dict)
        or not isinstance(recorded_cohort, dict)
        or not isinstance(recorded_precursor_policy, dict)
        or not isinstance(recorded_benchmark, dict)
    ):
        raise VerificationError(
            "research evaluation must contain evaluation, cohort_evaluation, and benchmark"
        )
    outcomes = observed.get("outcomes")
    if not isinstance(outcomes, list):
        raise VerificationError("research evaluator returned no outcomes")
    scenario_ids = tuple(item.get("scenario_id") for item in outcomes if isinstance(item, dict))
    if scenario_ids != _EXPECTED_SCENARIOS:
        raise VerificationError(f"unexpected research scenario IDs: {scenario_ids!r}")
    expected_count = len(_EXPECTED_SCENARIOS)
    if (
        observed.get("declared") != expected_count
        or observed.get("executed") != expected_count
        or not observed.get("passed")
    ):
        raise VerificationError("research evaluator did not pass all locked scenarios")
    recorded_fixture = evidence.get("fixture_sha256", recorded_eval.get("fixture_sha256"))
    if recorded_fixture != observed.get("fixture_sha256"):
        raise VerificationError("research fixture digest does not match the evaluator")
    recorded_scenarios = recorded_eval.get("scenario_ids", scenario_ids)
    if tuple(recorded_scenarios) != _EXPECTED_SCENARIOS:
        raise VerificationError("research evidence scenario inventory is not locked")
    if (
        recorded_eval.get("declared") != expected_count
        or recorded_eval.get("executed") != expected_count
        or not recorded_eval.get("passed")
    ):
        raise VerificationError("research evaluation evidence is not passing")
    observed_cohort = run_cohort_evaluator()
    cohort_outcomes = observed_cohort.get("outcomes")
    cohort_ids = (
        tuple(item.get("id") for item in cohort_outcomes if isinstance(item, dict))
        if isinstance(cohort_outcomes, list)
        else ()
    )
    if (
        cohort_ids != _EXPECTED_COHORT_SCENARIOS
        or observed_cohort.get("declared") != len(_EXPECTED_COHORT_SCENARIOS)
        or observed_cohort.get("executed") != len(_EXPECTED_COHORT_SCENARIOS)
        or not observed_cohort.get("passed")
    ):
        raise VerificationError("research cohort evaluator did not pass all locked scenarios")
    if recorded_cohort.get("fixture_sha256") != observed_cohort.get("fixture_sha256"):
        raise VerificationError("research cohort fixture digest does not match the evaluator")
    recorded_cohort_ids = recorded_cohort.get("scenario_ids", cohort_ids)
    if tuple(recorded_cohort_ids) != _EXPECTED_COHORT_SCENARIOS:
        raise VerificationError("research cohort scenario inventory is not locked")
    if (
        recorded_cohort.get("declared") != len(_EXPECTED_COHORT_SCENARIOS)
        or recorded_cohort.get("executed") != len(_EXPECTED_COHORT_SCENARIOS)
        or not recorded_cohort.get("passed")
    ):
        raise VerificationError("research cohort evidence is not passing")
    if recorded_cohort.get("outcomes") != cohort_outcomes:
        raise VerificationError("research cohort outcome projections are not locked")
    observed_precursor_policy = run_precursor_policy_evaluator()
    if (
        recorded_precursor_policy != observed_precursor_policy
        or observed_precursor_policy.get("passed") is not True
        or observed_precursor_policy.get("declared") != observed_precursor_policy.get("executed")
    ):
        raise VerificationError("research precursor-tolerance policy evidence is not passing")
    if recorded_benchmark.get("result_digest") != benchmark.get("result_digest"):
        raise VerificationError("research benchmark result digest changed")
    _verify_benchmark_record(recorded_benchmark)
    coverage = evidence.get("coverage")
    if coverage is not None and (
        not isinstance(coverage, dict)
        or float(coverage.get("percent", 0.0)) < float(coverage.get("fail_under", 95.0))
    ):
        raise VerificationError("research coverage evidence is below its fail-under threshold")
    return str(observed["fixture_sha256"])


def _verify_package(path: Path, receipt: dict[str, object]) -> None:
    if not path.is_file():
        raise VerificationError(f"package does not exist: {path}")
    filename = receipt.get("filename")
    expected_bytes = receipt.get("bytes")
    expected_sha = receipt.get("sha256")
    if not isinstance(filename, str) or path.name != filename:
        raise VerificationError(f"package filename does not match receipt: {path.name}")
    if type(expected_bytes) is not int or expected_bytes != path.stat().st_size:
        raise VerificationError(f"package size does not match receipt: {path.name}")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha.lower())
        or _sha256(path) != expected_sha.lower()
    ):
        raise VerificationError(f"package SHA-256 does not match receipt: {path.name}")
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


def _verify_package_receipt(  # noqa: C901
    path: Path,
    wheel: Path | None,
    sdist: Path | None,
    expected_fixture_sha256: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    evidence = _read_json(path)
    verification = evidence.get("verification")
    if not isinstance(verification, dict):
        raise VerificationError("research package evidence has no verification object")
    wheel_receipt = verification.get("wheel")
    sdist_receipt = verification.get("sdist")
    if not isinstance(wheel_receipt, dict) or not isinstance(sdist_receipt, dict):
        raise VerificationError("research package evidence has incomplete artifact receipts")
    for label, receipt in (("wheel", wheel_receipt), ("sdist", sdist_receipt)):
        digest = receipt.get("sha256")
        size = receipt.get("bytes")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest.lower())
            or type(size) is not int
            or size <= 0
        ):
            raise VerificationError(f"research {label} artifact receipt is malformed")
    if verification.get("reproducible_builds") != 2:
        raise VerificationError("research package evidence must record two reproducible builds")
    if verification.get("source_date_epoch") != _EXPECTED_SOURCE_DATE_EPOCH:
        raise VerificationError("research package evidence has an unexpected SOURCE_DATE_EPOCH")
    reproducible_hashes = verification.get("reproducible_hashes")
    if (
        not isinstance(reproducible_hashes, dict)
        or reproducible_hashes.get("wheel") != wheel_receipt.get("sha256")
        or reproducible_hashes.get("sdist") != sdist_receipt.get("sha256")
    ):
        raise VerificationError("research reproducibility hashes do not match artifact receipts")
    recorded_fixture = verification.get("fixture_sha256")
    if expected_fixture_sha256 is not None and recorded_fixture != expected_fixture_sha256:
        raise VerificationError("research package fixture digest does not match evaluation")
    cohort_fixture = verification.get("cohort_fixture_sha256")
    cohort_path = _ROOT / "tests" / "fixtures" / "research" / "cohort_scenarios.json"
    if cohort_fixture != _sha256(cohort_path):
        raise VerificationError("research package cohort fixture digest does not match source")
    if wheel is not None and sdist is not None:
        _verify_package(wheel, wheel_receipt)
        _verify_package(sdist, sdist_receipt)
    return wheel_receipt, sdist_receipt


def verify(
    evaluation: Path,
    wheel: Path | None = None,
    sdist: Path | None = None,
    package_evidence: Path = _EVIDENCE / "package.json",
    *,
    allow_metadata_only: bool = False,
) -> None:
    """Verify evaluator evidence and package reachability.

    Artifact-bound verification is the safe default.  Metadata-only checking is
    retained only for the source-only evaluator CI step and must be explicit.
    """

    fixture_sha256 = _verify_evaluation(evaluation)
    if (wheel is None) != (sdist is None):
        raise VerificationError("wheel and sdist must be supplied together")
    if wheel is not None and sdist is not None:
        _require_installed_research_runtime()
        _verify_package_receipt(package_evidence, wheel, sdist, fixture_sha256)
    elif allow_metadata_only:
        _verify_package_receipt(package_evidence, None, None, fixture_sha256)
    else:
        raise VerificationError("wheel and sdist are required for package verification")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("wheel", type=Path, nargs="?")
    parser.add_argument("sdist", type=Path, nargs="?")
    parser.add_argument("--package-evidence", type=Path, default=_EVIDENCE / "package.json")
    parser.add_argument(
        "--allow-metadata-only",
        action="store_true",
        help="skip artifact-byte verification (source-only evaluator mode)",
    )
    args = parser.parse_args()
    try:
        verify(
            args.evaluation,
            args.wheel,
            args.sdist,
            args.package_evidence,
            allow_metadata_only=args.allow_metadata_only,
        )
    except (OSError, KeyError, TypeError, ValueError, tarfile.TarError) as error:
        print(f"research pipeline verification failed: {error}", file=sys.stderr)
        return 1
    print("research pipeline verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
