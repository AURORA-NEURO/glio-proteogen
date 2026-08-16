"""Frozen caller-declared M24-04 transport fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m24_04 import (
    M2404_DOSSIER_SLICE,
    EvaluateBiomarkerPanelExternalTransportRequest,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
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


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim=f"Frozen M24-04 transport evidence from {M2404_DOSSIER_SLICE}.",
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"m2404.fixture.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="0.1.0",
        evidence=_artifact(f"m2404.fixture.{name}.evidence"),
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2404.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2404.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_artifact("m2404.fixture.identity.binding").digest,
                evidence=_artifact("m2404.fixture.identity.evidence"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="m2404.fixture.consent",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact("m2404.fixture.consent.evidence"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(name: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"Fixture does not estimate {name} uncertainty.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"m2404.fixture.validation.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="platform-1",
        specimen_description="frozen specimen",
        sample_count=25,
        provenance_artifact=_artifact(f"m2404.fixture.provenance.{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=(_evidence(f"m2404.fixture.validation.{dimension.value}"),),
    )


def _evaluation(
    dimension: TransportDimension,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"m2404.fixture.evaluation.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport_calibration",
        metric_value=0.92 if status is TransportStatus.SUPPORTED else 0.4,
        calibration_floor=0.8,
        rationale=(
            "Frozen fixture meets independent calibration floor."
            if status is TransportStatus.SUPPORTED
            else "Frozen fixture demonstrates a calibration-floor failure."
        ),
        evidence=(_evidence(f"m2404.fixture.evaluation.{dimension.value}"),),
    )


def build_request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    """Return the frozen normal external transport request."""

    request_id = "m2404.fixture.request"
    inputs = (
        _artifact("m2404.fixture.mass-spectrometry-proteome"),
        _artifact("m2404.fixture.genome-transcriptome"),
        _artifact("m2404.fixture.ptm-annotations"),
        _artifact("m2404.fixture.benchmark-package"),
    )
    return EvaluateBiomarkerPanelExternalTransportRequest(
        request_id=request_id,
        context=_context(request_id),
        mass_spectrometry_proteome=inputs[0],
        genome_transcriptome=inputs[1],
        ptm_annotations=inputs[2],
        benchmark_package=inputs[3],
        validations=tuple(_validation(dimension) for dimension in TransportDimension),
        evaluations=tuple(_evaluation(dimension) for dimension in TransportDimension),
        configuration=TransportConfiguration(
            configuration_id="m2404.fixture.configuration",
            version="0.1.0",
            required_dimensions=tuple(TransportDimension),
            minimum_calibration_floor=0.8,
            evidence=(_evidence("m2404.fixture.configuration"),),
        ),
        source_artifacts=inputs,
    )


def denied_request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    """Return a request denied by the support control."""

    request = build_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": rejected})
    context = request.context.model_copy(update={"references": references})
    return request.model_copy(update={"context": context})


def narrowed_request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    """Return a request with one failed calibration floor."""

    request = build_request()
    failed = request.evaluations[0].model_copy(
        update={"status": TransportStatus.DOMAIN_NARROWED, "metric_value": 0.4}
    )
    return request.model_copy(update={"evaluations": (failed, *request.evaluations[1:])})


def not_evaluable_request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    """Return a request with an explicit not-evaluable dimension."""

    request = build_request()
    missing = request.evaluations[0].model_copy(update={"status": TransportStatus.NOT_EVALUABLE})
    return request.model_copy(update={"evaluations": (missing, *request.evaluations[1:])})


__all__ = ["build_request", "denied_request", "narrowed_request", "not_evaluable_request"]
