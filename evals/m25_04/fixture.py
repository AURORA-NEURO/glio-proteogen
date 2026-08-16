"""Caller-declared deterministic M25-04 transport fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m25_04 import (
    M2504_M2503_INPUT_MEDIA_TYPE,
    EvaluateProteotypeExternalTransportRequest,
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
    SemanticVersion,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

FIXTURE_REQUEST_ID = "m2504-fixture-request"
FIXTURE_VERSION = SemanticVersion("1.0.0")
FIXTURE_DIGEST = "sha256:" + ("c" * 64)
DIMENSIONS = tuple(TransportDimension)


def artifact(
    artifact_id: str,
    media_type: str = "application/octet-stream",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=FIXTURE_VERSION,
        digest=FIXTURE_DIGEST,
        media_type=media_type,
    )


def evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact("m2504.fixture.evidence"),
            role="evidence",
            claim="Caller-declared locked external transport fixture evidence.",
        ),
    )


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact("m2504.fixture.control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2504.fixture-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2504.fixture.configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2504.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=FIXTURE_DIGEST,
                evidence=control_evidence,
            ),
            provenance=decision("m2504.fixture.provenance"),
            consent=ConsentReference(
                decision_id="m2504.fixture.consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2504.fixture.quality"),
            support=decision("m2504.fixture.support"),
            intended_use=decision("m2504.fixture.intended-use"),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.5,
        rationale="Caller-declared external transport uncertainty.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"m2504.validation.{dimension.value}",
        dimension=dimension,
        source_domain=f"source-{dimension.value}",
        target_domain=f"target-{dimension.value}",
        assay_or_platform="structure-aware proteoform model",
        specimen_description="Frozen glioma specimen",
        sample_count=12,
        provenance_artifact=artifact(f"m2504.provenance.{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=evidence(),
    )


def _evaluation(
    dimension: TransportDimension,
    *,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> TransportEvaluation:
    floor = 0.8
    value = 0.9 if status is TransportStatus.SUPPORTED else 0.6
    return TransportEvaluation(
        evaluation_id=f"m2504.evaluation.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="balanced_transport_score",
        metric_value=value,
        calibration_floor=floor,
        rationale="Caller-declared external validation result.",
        evidence=evidence(),
    )


def build_request(
    *,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> EvaluateProteotypeExternalTransportRequest:
    benchmark = artifact("m2503.fixture.benchmark", M2504_M2503_INPUT_MEDIA_TYPE)
    return EvaluateProteotypeExternalTransportRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        mass_spectrometry_proteome=artifact("m2504.fixture.proteome"),
        genome_transcriptome=artifact("m2504.fixture.genome-transcriptome"),
        ptm_annotations=artifact("m2504.fixture.ptm"),
        benchmark_package=benchmark,
        validations=tuple(_validation(dimension) for dimension in DIMENSIONS),
        evaluations=tuple(
            _evaluation(
                dimension,
                status=(
                    status
                    if status is not TransportStatus.DOMAIN_NARROWED
                    or dimension is TransportDimension.SITE
                    else TransportStatus.SUPPORTED
                ),
            )
            for dimension in DIMENSIONS
        ),
        configuration=TransportConfiguration(
            configuration_id="m2504.fixture.configuration",
            version=FIXTURE_VERSION,
            required_dimensions=DIMENSIONS,
            minimum_calibration_floor=0.8,
            evidence=evidence(),
        ),
        source_artifacts=(benchmark, artifact("m2504.fixture.policy")),
    )


def denied_request() -> EvaluateProteotypeExternalTransportRequest:
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


def not_evaluable_request() -> EvaluateProteotypeExternalTransportRequest:
    return build_request(status=TransportStatus.NOT_EVALUABLE)


__all__ = [
    "DIMENSIONS",
    "FIXTURE_DIGEST",
    "FIXTURE_REQUEST_ID",
    "build_request",
    "context",
    "denied_request",
    "not_evaluable_request",
]
