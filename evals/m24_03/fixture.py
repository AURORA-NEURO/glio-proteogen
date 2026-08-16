"""Frozen caller-declared M24-03 benchmark fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m24_03 import (
    M2403_M2402_INPUT_MEDIA_TYPE,
    BaselineKind,
    BaselineRun,
    BenchmarkMetric,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunBiomarkerPanelInternalBenchmarkRequest,
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
        claim="Frozen M24-03 internal benchmark fixture evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    artifact = _artifact("m2403.context")
    accepted = UpstreamDecisionReference(
        decision_id="m2403.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2403.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2403.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2403.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _metric(name: str, *, status: ValidationStatus = ValidationStatus.PASS) -> BenchmarkMetric:
    return BenchmarkMetric(
        metric_id=name + ".metric",
        metric_name="balanced_accuracy",
        baseline_value=0.5,
        candidate_value=0.55,
        tolerance=0.1,
        status=status,
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


def build_request() -> RunBiomarkerPanelInternalBenchmarkRequest:
    """Return the frozen normal benchmark request."""

    upstream = _artifact("m2403.m2402.synthetic.truth", M2403_M2402_INPUT_MEDIA_TYPE)
    return RunBiomarkerPanelInternalBenchmarkRequest(
        request_id="m2403.fixture.request",
        context=_context("m2403.fixture.request"),
        upstream_result=upstream,
        split=LockedSplit(
            split_id="m2403.locked.split",
            version="1.0.0",
            train_examples=10,
            validation_examples=5,
            test_examples=5,
            random_seed=17,
            evidence=(_evidence("m2403.split.evidence"),),
        ),
        baseline_runs=(
            _baseline("m2403.simple", BaselineKind.SIMPLE),
            _baseline("m2403.mature", BaselineKind.MATURE),
        ),
        ablations=(
            ComponentAblation(
                ablation_id="m2403.pathway.ablation",
                component="pathway_context",
                with_component_score=0.8,
                without_component_score=0.6,
                score_delta=0.2,
                compute_units=10.0,
                status=ValidationStatus.PASS,
                evidence=(_evidence("m2403.ablation.evidence"),),
            ),
        ),
        comparisons=(
            ComputeMatchedComparison(
                comparison_id="m2403.simple.vs.mature",
                reference_run_id="m2403.simple",
                candidate_run_id="m2403.mature",
                reference_compute_units=10.0,
                candidate_compute_units=10.0,
                compute_tolerance=0.0,
                reference_score=0.5,
                candidate_score=0.55,
                status=ValidationStatus.PASS,
                evidence=(_evidence("m2403.comparison.evidence"),),
            ),
        ),
        source_artifacts=(upstream, _artifact("m2403.benchmark.material")),
    )


def denied_request() -> RunBiomarkerPanelInternalBenchmarkRequest:
    """Return a request denied by the caller-declared support control."""

    request = build_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    return request.model_copy(update={"context": context})


def not_evaluable_request() -> RunBiomarkerPanelInternalBenchmarkRequest:
    """Return a request with explicit missing/not-evaluable evidence."""

    request = build_request()
    metric = (
        request.baseline_runs[0]
        .metrics[0]
        .model_copy(update={"status": ValidationStatus.NOT_EVALUABLE})
    )
    baseline = request.baseline_runs[0].model_copy(update={"metrics": (metric,)})
    return request.model_copy(update={"baseline_runs": (baseline, *request.baseline_runs[1:])})


__all__ = ["build_request", "denied_request", "not_evaluable_request"]
