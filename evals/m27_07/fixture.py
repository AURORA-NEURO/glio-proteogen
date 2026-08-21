"""Deterministic caller-declared M27-07 change-control workload."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m27_07 import (
    ChampionChallengerComparison,
    ChangeClassification,
    ChangeKind,
    ChangeRisk,
    ComparisonStatus,
    ControlComplexActivityChangeRequest,
    MetricComparison,
    RevalidationPlan,
    RollbackPoint,
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


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2707.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _decision(
    label: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"m2707.decision.{label}",
        state=state,
        policy_version="1.0.0",
        evidence=_artifact(f"decision-{label}"),
    )


def _context(request_id: str, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="m2707.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_artifact("identity-binding").digest,
            evidence=_artifact("identity"),
        ),
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="m2707.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended-use"),
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2707.actor.operator",
        occurred_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
        references=refs,
    )


def build_request(
    request_id: str = "m2707.request.default",
    *,
    upstream_media_type: str = "application/vnd.glio-proteogen.m27-06+json",
    consent: ConsentState = ConsentState.GRANTED,
    challenger_regression: bool = False,
) -> ControlComplexActivityChangeRequest:
    champion = _artifact("champion", upstream_media_type).digest
    challenger = _artifact("challenger", upstream_media_type).digest
    metric = MetricComparison(
        metric="security-regression-rate",
        champion_value=0.10,
        challenger_value=0.20 if challenger_regression else 0.10,
        tolerance=0.05,
        within_tolerance=not challenger_regression,
        evidence=(
            EvidenceReference(reference=_artifact("metric"), role="evidence", claim="metric"),
        ),
    )
    evidence = (_artifact("classification"),)
    classification = ChangeClassification(
        change_id="m2707.change.default",
        kind=ChangeKind.POLICY,
        risk=ChangeRisk.HIGH,
        summary="Update caller-declared security access policy",
        impact_scope=("access-policy", "complex-activity-service"),
        evidence=tuple(
            EvidenceReference(reference=item, role="evidence", claim="change classification")
            for item in evidence
        ),
    )
    revalidation = RevalidationPlan(
        plan_id="m2707.plan.default",
        version="1.0.0",
        required_checks=("schema", "security", "rollback"),
        completed_checks=("schema", "security", "rollback"),
        validation_digest=_artifact("validation").digest,
        evidence=(
            EvidenceReference(
                reference=_artifact("revalidation"), role="evidence", claim="revalidation"
            ),
        ),
    )
    rollback = RollbackPoint(
        rollback_id="m2707.rollback.default",
        version="1.0.0",
        target_digest=_artifact("rollback-target").digest,
        rollback_reason="Restore the last approved security policy",
        evidence=(
            EvidenceReference(
                reference=_artifact("rollback"), role="evidence", claim="rollback test"
            ),
        ),
    )
    request = ControlComplexActivityChangeRequest(
        request_id=request_id,
        context=_context(request_id, consent),
        upstream_result=_artifact("upstream", upstream_media_type),
        classification=classification,
        revalidation=revalidation,
        champion_digest=champion,
        challenger_digest=challenger,
        rollback_point=rollback,
        source_artifacts=(
            _artifact("upstream", upstream_media_type),
            _artifact("champion", upstream_media_type),
            _artifact("challenger", upstream_media_type),
            _artifact("classification"),
            _artifact("revalidation"),
            _artifact("rollback"),
            _artifact("source-regression-a" if challenger_regression else "source-a"),
            _artifact("source-b"),
        ),
    )
    # Construct the comparison to exercise the frozen contract fields before runtime.
    _ = ChampionChallengerComparison(
        comparison_id="m2707.comparison.default",
        champion_digest=champion,
        challenger_digest=challenger,
        status=ComparisonStatus.FAILED if challenger_regression else ComparisonStatus.PASSED,
        metrics=(metric,),
        evidence=(
            EvidenceReference(
                reference=_artifact("comparison"), role="evidence", claim="comparison"
            ),
        ),
    )
    return request


__all__ = ["build_request"]
