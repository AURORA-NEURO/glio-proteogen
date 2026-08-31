"""Low-disk executable performance checks for the functional-proteotype demo."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest
from benchmarks.research_gbm_functional_proteotype import (
    DEMO_P95_THRESHOLD_SECONDS,
    EVIDENCE_SCHEMA_VERSION,
    EXECUTION_ISOLATION,
    MAXIMUM_BOOTSTRAP_REPLICATES,
    MAXIMUM_OBSERVATION_COUNT,
    MAXIMUM_PERMUTATION_REPLICATES,
    MAXIMUM_REQUEST_DIGEST,
    MAXIMUM_RESAMPLING_EVIDENCE_SCHEMA_VERSION,
    MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS,
    MAXIMUM_RESAMPLING_PROFILE,
    MAXIMUM_RESAMPLING_SCENARIO,
    DemoPerformanceEvidence,
    MaximumResamplingPerformanceEvidence,
    maximum_resampling_request,
    nearest_rank_percentile,
    run_demo_benchmark,
    run_maximum_resampling_benchmark,
)
from pydantic import ValidationError

from glio_proteogen.research.gbm_functional_proteotype import (
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    demo_request_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.canonical import canonical_json_bytes

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _receipt(**updates: object) -> DemoPerformanceEvidence:
    payload: dict[str, object] = {
        "fixture_digest": DIGEST_A,
        "profile_digest": DIGEST_B,
        "result_digest": DIGEST_C,
        "numpy_version": "2.5.2",
        "python_version": "3.12.13",
        "platform": "test-platform",
        "request_bytes": 1_024,
        "result_bytes": 2_048,
        "warmup_runs": 0,
        "measured_runs": 2,
        "durations_seconds": (0.5, 0.8),
        "p95_seconds": 0.8,
        "passed": True,
    }
    payload.update(updates)
    return DemoPerformanceEvidence.model_validate(payload, strict=True)


def _maximum_receipt(**updates: object) -> MaximumResamplingPerformanceEvidence:
    payload: dict[str, object] = {
        "fixture_digest": MAXIMUM_REQUEST_DIGEST,
        "profile_digest": DIGEST_B,
        "result_digest": DIGEST_C,
        "numpy_version": "2.5.2",
        "python_version": "3.12.13",
        "platform": "test-platform",
        "request_bytes": 153_523,
        "result_bytes": 2_048,
        "warmup_runs": 0,
        "measured_runs": 2,
        "durations_seconds": (4.5, 5.8),
        "p95_seconds": 5.8,
        "passed": True,
    }
    payload.update(updates)
    return MaximumResamplingPerformanceEvidence.model_validate(payload, strict=True)


def test_performance_receipt_is_versioned_strict_and_self_consistent() -> None:
    receipt = _receipt()
    schema = DemoPerformanceEvidence.model_json_schema()

    assert receipt.schema_version == EVIDENCE_SCHEMA_VERSION
    assert receipt.execution_isolation == EXECUTION_ISOLATION
    assert schema["additionalProperties"] is False
    assert (
        DemoPerformanceEvidence.model_validate_json(
            canonical_json_bytes(receipt.model_dump(mode="json")),
            strict=True,
        )
        == receipt
    )

    with pytest.raises(ValidationError, match="duration count"):
        _receipt(measured_runs=3)
    with pytest.raises(ValidationError, match="reported p95"):
        _receipt(p95_seconds=0.7)
    with pytest.raises(ValidationError, match="pass state"):
        _receipt(passed=False)


def test_nearest_rank_percentile_is_deterministic_and_validated() -> None:
    assert nearest_rank_percentile((0.5, 0.1, 0.4, 0.2, 0.3), 95) == 0.5
    assert nearest_rank_percentile((0.5,), 95) == 0.5
    with pytest.raises(ValueError, match="at least one"):
        nearest_rank_percentile((), 95)
    with pytest.raises(ValueError, match=r"\[1, 100\]"):
        nearest_rank_percentile((0.1,), 0)


def test_maximum_resampling_fixture_and_receipt_are_exactly_locked() -> None:
    request = maximum_resampling_request()
    receipt = _maximum_receipt()

    assert request.request_digest == MAXIMUM_REQUEST_DIGEST
    assert len(request.observations) == MAXIMUM_OBSERVATION_COUNT
    assert len({item.gene_symbol for item in request.observations}) == 600
    assert all(item.state.value == "observed" for item in request.observations)
    assert request.bootstrap_replicates == MAXIMUM_BOOTSTRAP_REPLICATES
    assert request.permutation_replicates == MAXIMUM_PERMUTATION_REPLICATES
    assert receipt.schema_version == MAXIMUM_RESAMPLING_EVIDENCE_SCHEMA_VERSION
    assert receipt.scenario == MAXIMUM_RESAMPLING_SCENARIO
    assert receipt.resampling_profile == MAXIMUM_RESAMPLING_PROFILE
    assert receipt.p95_threshold_seconds == MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS

    with pytest.raises(ValidationError, match="fixture digest"):
        _maximum_receipt(fixture_digest=DIGEST_A)
    with pytest.raises(ValidationError, match="exactly ten seconds"):
        _maximum_receipt(p95_threshold_seconds=9.0)
    with pytest.raises(ValidationError, match="pass state"):
        _maximum_receipt(passed=False)


@pytest.mark.benchmark
def test_synthetic_demo_is_deterministic_and_meets_the_p95_gate() -> None:
    evidence = run_demo_benchmark(warmup_runs=0, measured_runs=2)

    assert evidence.passed
    assert evidence.deterministic
    assert evidence.fixture_digest == demo_request_digest()
    assert evidence.observation_count == 108
    assert evidence.bootstrap_replicates == 64
    assert evidence.permutation_replicates == 256
    assert evidence.p95_seconds < DEMO_P95_THRESHOLD_SECONDS
    assert evidence.request_bytes <= MAX_REQUEST_BYTES
    assert evidence.result_bytes <= MAX_RESULT_BYTES


@pytest.mark.benchmark
def test_all_catalog_proteins_at_maximum_resampling_meet_the_p95_gate() -> None:
    evidence = run_maximum_resampling_benchmark(warmup_runs=0, measured_runs=2)

    assert evidence.passed
    assert evidence.deterministic
    assert evidence.fixture_digest == MAXIMUM_REQUEST_DIGEST
    assert evidence.scenario == MAXIMUM_RESAMPLING_SCENARIO
    assert evidence.resampling_profile == MAXIMUM_RESAMPLING_PROFILE
    assert evidence.observation_count == MAXIMUM_OBSERVATION_COUNT
    assert evidence.active_catalog_protein_count == MAXIMUM_OBSERVATION_COUNT
    assert evidence.bootstrap_replicates == MAXIMUM_BOOTSTRAP_REPLICATES
    assert evidence.permutation_replicates == MAXIMUM_PERMUTATION_REPLICATES
    assert evidence.bootstrap_replicates_used == MAXIMUM_BOOTSTRAP_REPLICATES
    assert evidence.permutation_replicates_used == MAXIMUM_PERMUTATION_REPLICATES
    assert evidence.solver_converged
    assert evidence.axis_output_count == 4
    assert evidence.supported_axis_output_count == 4
    assert evidence.ablation_output_count == 52
    assert evidence.p95_seconds < MAXIMUM_RESAMPLING_P95_THRESHOLD_SECONDS
    assert evidence.request_bytes <= MAX_REQUEST_BYTES
    assert evidence.result_bytes <= MAX_RESULT_BYTES
