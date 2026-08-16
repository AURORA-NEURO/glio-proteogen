"""Frozen caller-declared M21-03 benchmark fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m21_03 import (
    M2103_M2102_INPUT_MEDIA_TYPE,
    BaselineKind,
    BaselineRun,
    BenchmarkMetric,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunComplexActivityInternalBenchmarkRequest,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Frozen M21-03 benchmark fixture evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    artifact = _artifact("m2103.context")
    accepted = UpstreamDecisionReference(
        decision_id="m2103.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2103.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2103.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2103.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _metric(name: str) -> BenchmarkMetric:
    return BenchmarkMetric(
        metric_id=name + ".metric",
        metric_name="balanced_accuracy",
        baseline_value=0.5,
        candidate_value=0.7,
        tolerance=0.1,
        status=ValidationStatus.PASS,
        evidence=(_evidence(name + ".metric.evidence"),),
    )


def _baseline(name: str, kind: BaselineKind) -> BaselineRun:
    return BaselineRun(
        run_id=name,
        kind=kind,
        model_name=name + ".model",
        compute_units=10.0,
        metrics=(_metric(name),),
        evidence=(_evidence(name + ".evidence"),),
    )


def build_request() -> RunComplexActivityInternalBenchmarkRequest:
    """Return the frozen normal benchmark request."""

    upstream = _artifact("m2102.synthetic.truth", M2103_M2102_INPUT_MEDIA_TYPE)
    return RunComplexActivityInternalBenchmarkRequest(
        request_id="m2103.fixture.request",
        context=_context("m2103.fixture.request"),
        upstream_result=upstream,
        split=LockedSplit(
            split_id="m2103.locked.split",
            version="1.0.0",
            train_examples=10,
            validation_examples=5,
            test_examples=5,
            random_seed=17,
            evidence=(_evidence("m2103.split.evidence"),),
        ),
        baseline_runs=(
            _baseline("m2103.simple", BaselineKind.SIMPLE),
            _baseline("m2103.mature", BaselineKind.MATURE),
        ),
        ablations=(
            ComponentAblation(
                ablation_id="m2103.pathway.ablation",
                component="pathway_context",
                with_component_score=0.8,
                without_component_score=0.6,
                score_delta=0.2,
                compute_units=10.0,
                status=ValidationStatus.PASS,
                evidence=(_evidence("m2103.ablation.evidence"),),
            ),
        ),
        comparisons=(
            ComputeMatchedComparison(
                comparison_id="m2103.simple.vs.mature",
                reference_run_id="m2103.simple",
                candidate_run_id="m2103.mature",
                reference_compute_units=10.0,
                candidate_compute_units=10.0,
                compute_tolerance=0.0,
                reference_score=0.5,
                candidate_score=0.7,
                status=ValidationStatus.PASS,
                evidence=(_evidence("m2103.comparison.evidence"),),
            ),
        ),
        source_artifacts=(upstream, _artifact("m2103.benchmark.material")),
    )


def denied_request() -> RunComplexActivityInternalBenchmarkRequest:
    """Return a request denied by the caller-declared support control."""

    request = build_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    return request.model_copy(update={"context": context})


__all__ = ["build_request", "denied_request"]
