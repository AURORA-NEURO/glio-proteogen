"""Caller-declared deterministic M25-03 benchmark fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

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

FIXTURE_REQUEST_ID = "m2503-fixture-request"
FIXTURE_DIGEST = "sha256:" + ("b" * 64)
FIXTURE_VERSION = "1.0.0"


def artifact(artifact_id: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=FIXTURE_VERSION,
        digest=FIXTURE_DIGEST,
        media_type=media_type,
    )


def evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact("m2503-fixture-evidence"),
            role="evidence",
            claim="Caller-declared locked benchmark fixture evidence.",
        ),
    )


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact("m2503-control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2503-fixture-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2503-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2503-identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=FIXTURE_DIGEST,
                evidence=control_evidence,
            ),
            provenance=decision("m2503-provenance"),
            consent=ConsentReference(
                decision_id="m2503-consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2503-quality"),
            support=decision("m2503-support"),
            intended_use=decision("m2503-intended-use"),
        ),
    )


def split() -> LockedSplit:
    return LockedSplit(
        split_id="m2503-locked-split",
        version=FIXTURE_VERSION,
        train_examples=8,
        validation_examples=4,
        test_examples=4,
        random_seed=13,
        evidence=evidence(),
    )


def baseline(
    run_id: str = "m2503-baseline-simple",
    *,
    status: ValidationStatus = ValidationStatus.PASS,
) -> BaselineRun:
    metric = BenchmarkMetric(
        metric_id=f"{run_id}-metric",
        metric_name="balanced_accuracy",
        baseline_value=0.8,
        candidate_value=0.82,
        tolerance=0.01,
        status=status,
        evidence=evidence(),
    )
    return BaselineRun(
        run_id=run_id,
        kind=BaselineKind.SIMPLE,
        model_name="m2503-deterministic-baseline",
        compute_units=4.0,
        metrics=(metric,),
        evidence=evidence(),
    )


def ablation(*, status: ValidationStatus = ValidationStatus.PASS) -> ComponentAblation:
    return ComponentAblation(
        ablation_id="m2503-ablation-interaction",
        component="interaction_features",
        with_component_score=0.82,
        without_component_score=0.8,
        score_delta=0.02,
        compute_units=4.0,
        status=status,
        evidence=evidence(),
    )


def comparison(
    run_id: str = "m2503-baseline-simple",
    *,
    status: ValidationStatus = ValidationStatus.PASS,
) -> ComputeMatchedComparison:
    return ComputeMatchedComparison(
        comparison_id="m2503-comparison-simple",
        reference_run_id=run_id,
        candidate_run_id=run_id,
        reference_compute_units=4.0,
        candidate_compute_units=4.0,
        compute_tolerance=0.0,
        reference_score=0.8,
        candidate_score=0.82,
        status=status,
        evidence=evidence(),
    )


def build_request(
    *,
    metric_status: ValidationStatus = ValidationStatus.PASS,
    ablation_status: ValidationStatus = ValidationStatus.PASS,
    comparison_status: ValidationStatus = ValidationStatus.PASS,
) -> RunProteotypeInternalBenchmarkRequest:
    upstream = artifact("m2503-upstream-result", M2503_M2502_INPUT_MEDIA_TYPE)
    baseline_run = baseline(status=metric_status)
    return RunProteotypeInternalBenchmarkRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        upstream_result=upstream,
        split=split(),
        baseline_runs=(baseline_run,),
        ablations=(ablation(status=ablation_status),),
        comparisons=(comparison(status=comparison_status),),
        source_artifacts=(upstream,),
    )


def denied_request() -> RunProteotypeInternalBenchmarkRequest:
    request = build_request()
    references = request.context.references
    denied = references.support.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"support": denied})}
            )
        }
    )


__all__ = [
    "FIXTURE_DIGEST",
    "FIXTURE_REQUEST_ID",
    "build_request",
    "context",
    "denied_request",
]
