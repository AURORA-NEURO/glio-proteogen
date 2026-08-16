"""Adversarial closure tests for the M25-03 benchmark contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m25_03 import (
    M2503_M2502_INPUT_MEDIA_TYPE,
    BaselineKind,
    BaselineRun,
    BenchmarkMetric,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunProteotypeInternalBenchmarkRequest,
    ValidationStatus,
    result_identifier,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_DIGEST = "sha256:" + ("a" * 64)
_VERSION = "1.0.0"


def _artifact(artifact_id: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=_VERSION,
        digest=_DIGEST,
        media_type=media_type,
    )


def _context(request_id: str) -> ExecutionContext:
    evidence = _artifact("control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=_VERSION,
            evidence=evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="benchmark-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=_VERSION,
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="consent",
                state=ConsentState.GRANTED,
                policy_version=_VERSION,
                evidence=evidence,
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact("evidence"),
            role="evidence",
            claim="caller-declared benchmark evidence",
        ),
    )


def _split() -> LockedSplit:
    return LockedSplit(
        split_id="locked-split",
        version=_VERSION,
        train_examples=8,
        validation_examples=4,
        test_examples=4,
        random_seed=7,
        evidence=_evidence(),
    )


def _baseline(run_id: str = "baseline-simple") -> BaselineRun:
    metric = BenchmarkMetric(
        metric_id=f"metric-{run_id}",
        metric_name="balanced_accuracy",
        baseline_value=0.8,
        candidate_value=0.82,
        tolerance=0.01,
        status=ValidationStatus.PASS,
        evidence=_evidence(),
    )
    return BaselineRun(
        run_id=run_id,
        kind=BaselineKind.SIMPLE,
        model_name="deterministic-baseline",
        compute_units=4.0,
        metrics=(metric,),
        evidence=_evidence(),
    )


def _comparison(run_id: str = "baseline-simple") -> ComputeMatchedComparison:
    return ComputeMatchedComparison(
        comparison_id="comparison-1",
        reference_run_id=run_id,
        candidate_run_id=run_id,
        reference_compute_units=4.0,
        candidate_compute_units=4.0,
        compute_tolerance=0.0,
        reference_score=0.8,
        candidate_score=0.82,
        status=ValidationStatus.PASS,
        evidence=_evidence(),
    )


def _ablation() -> ComponentAblation:
    return ComponentAblation(
        ablation_id="ablation-interaction",
        component="interaction_features",
        with_component_score=0.82,
        without_component_score=0.8,
        score_delta=0.02,
        compute_units=4.0,
        status=ValidationStatus.PASS,
        evidence=_evidence(),
    )


def _request() -> RunProteotypeInternalBenchmarkRequest:
    request_id = "benchmark-request"
    upstream = _artifact("upstream-result", M2503_M2502_INPUT_MEDIA_TYPE)
    baseline = _baseline()
    return RunProteotypeInternalBenchmarkRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=upstream,
        split=_split(),
        baseline_runs=(baseline,),
        ablations=(_ablation(),),
        comparisons=(_comparison(),),
        source_artifacts=(upstream,),
    )


def test_result_identifier_is_stable_and_status_bound() -> None:
    request = _request()
    assert result_identifier(request, "completed") == result_identifier(request, "completed")
    assert result_identifier(request, "completed") != result_identifier(request, "abstained")


def test_upstream_media_type_is_closed() -> None:
    request = _request().model_copy(
        update={"upstream_result": _artifact("upstream-result", "application/json")}
    )
    with pytest.raises(ValidationError, match="M25-02"):
        RunProteotypeInternalBenchmarkRequest.model_validate(request.model_dump(mode="python"))


def test_context_request_id_is_closed() -> None:
    request = _request().model_copy(update={"context": _context("different-request")})
    with pytest.raises(ValidationError, match="context request id"):
        RunProteotypeInternalBenchmarkRequest.model_validate(request.model_dump(mode="python"))


def test_upstream_must_be_present_in_source_artifacts() -> None:
    request = _request().model_copy(update={"source_artifacts": (_artifact("other-source"),)})
    with pytest.raises(ValidationError, match="include the declared upstream"):
        RunProteotypeInternalBenchmarkRequest.model_validate(request.model_dump(mode="python"))


def test_comparison_must_reference_declared_baselines() -> None:
    request = _request().model_copy(update={"comparisons": (_comparison("unknown-baseline"),)})
    with pytest.raises(ValidationError, match="declared baseline"):
        RunProteotypeInternalBenchmarkRequest.model_validate(request.model_dump(mode="python"))


def test_duplicate_baselines_are_rejected() -> None:
    request = _request()
    request_data = request.model_dump(mode="python")
    request_data["baseline_runs"] = (request.baseline_runs[0], request.baseline_runs[0])
    with pytest.raises(ValidationError, match="baseline run identifiers"):
        RunProteotypeInternalBenchmarkRequest.model_validate(request_data)


def test_ablation_score_delta_is_canonical() -> None:
    with pytest.raises(ValidationError, match="score delta"):
        ComponentAblation.model_validate(
            _ablation().model_copy(update={"score_delta": 0.4}).model_dump(mode="python")
        )

