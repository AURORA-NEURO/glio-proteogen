"""Frozen caller-declared M25-01 reference-truth scenarios."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m25_01 import (
    AdjudicationRecord,
    AdjudicationStatus,
    BenchmarkConfiguration,
    CurateProteotypeReferenceTruthRequest,
    EndpointDefinition,
    InclusionDecision,
    ReferenceEntry,
    ReferenceKind,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type="application/json",
    )


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact(name),
        role="evidence",
        claim="Frozen caller-declared M25-01 benchmark evidence.",
    )


def _uncertainty() -> UncertaintyProfile:
    unavailable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M25-01 does not infer uncertainty from fixture content.",
    )
    return UncertaintyProfile(
        measurement=unavailable,
        sampling=unavailable,
        parameter=unavailable,
        model_form=unavailable,
        identification=unavailable,
        support=unavailable,
        transport=unavailable,
    )


def entry(identifier: str, kind: ReferenceKind) -> ReferenceEntry:
    return ReferenceEntry(
        reference_id=identifier,
        kind=kind,
        artifact=artifact(identifier),
        expected_label="known proteotype reference",
        inclusion_reason="registered fixture material",
        provenance_artifact=artifact(identifier + ".provenance"),
        challenge_set=kind is ReferenceKind.CHALLENGE_SET,
        uncertainty=_uncertainty(),
        evidence=(evidence(identifier + ".evidence"),),
    )


def context(request_id: str = "fixture-request") -> ExecutionContext:
    control_artifact = artifact("fixture-control")
    accepted = UpstreamDecisionReference(
        decision_id="fixture-accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=control_artifact,
    )
    identity = IdentityLineageReference(
        decision_id="fixture-identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=control_artifact.digest,
        evidence=control_artifact,
    )
    consent = ConsentReference(
        decision_id="fixture-consent",
        state=ConsentState.GRANTED,
        policy_version="1.0.0",
        evidence=control_artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="fixture-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=identity,
            provenance=accepted,
            consent=consent,
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def build_request() -> CurateProteotypeReferenceTruthRequest:
    references = (
        entry("fixture-calibrator", ReferenceKind.CALIBRATOR),
        entry("fixture-challenge", ReferenceKind.CHALLENGE_SET),
    )
    controls = (
        entry("fixture-positive", ReferenceKind.POSITIVE_CONTROL),
        entry("fixture-negative", ReferenceKind.NEGATIVE_CONTROL),
    )
    ids = tuple(item.reference_id for item in (*references, *controls))
    return CurateProteotypeReferenceTruthRequest(
        request_id="fixture-request",
        context=context(),
        endpoint=EndpointDefinition(
            endpoint_id="fixture-endpoint",
            name="Frozen proteotype endpoint",
            definition="Caller-declared reference truth endpoint.",
            metric="calibration_error",
            acceptance_tolerance="Within frozen fixture tolerance.",
            evidence=(evidence("fixture-endpoint.evidence"),),
        ),
        references=references,
        controls=controls,
        inclusions=tuple(
            InclusionDecision(
                reference_id=identifier,
                included=True,
                rationale="fixture item meets inclusion policy",
                leakage_audit="fixture partition leakage audit passed",
                evidence=(evidence(identifier + ".inclusion"),),
            )
            for identifier in ids
        ),
        adjudications=tuple(
            AdjudicationRecord(
                reference_id=identifier,
                status=AdjudicationStatus.LOCKED,
                reviewer_tokens=("fixture-reviewer-a", "fixture-reviewer-b"),
                agreement_statement="Independent fixture reviewers agree.",
                evidence=(evidence(identifier + ".adjudication"),),
            )
            for identifier in ids
        ),
        configuration=BenchmarkConfiguration(
            configuration_id="fixture-configuration",
            version="0.1.0",
        ),
        source_artifacts=(artifact("fixture-source"),),
    )


def pending_request() -> CurateProteotypeReferenceTruthRequest:
    request = build_request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.PENDING})
    return request.model_copy(update={"adjudications": (pending, *request.adjudications[1:])})


def rejected_included_request() -> CurateProteotypeReferenceTruthRequest:
    request = build_request()
    rejected = request.adjudications[0].model_copy(
        update={
            "status": AdjudicationStatus.REJECTED,
            "disagreement_statement": "Fixture reviewers rejected the item.",
        }
    )
    return request.model_copy(update={"adjudications": (rejected, *request.adjudications[1:])})


def denied_request() -> CurateProteotypeReferenceTruthRequest:
    request = build_request()
    denied_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": denied_support})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


__all__ = [
    "build_request",
    "denied_request",
    "pending_request",
    "rejected_included_request",
]
