"""Adversarial M25-04 contract closure tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m25_04 import (
    M2504_M2503_INPUT_MEDIA_TYPE,
    EvaluateProteotypeExternalTransportRequest,
    SupportDomainUpdate,
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

_VERSION = SemanticVersion("1.0.0")
_DIGEST = "sha256:" + ("a" * 64)
_DIMENSIONS = tuple(TransportDimension)


def _artifact(name: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name, version=_VERSION, digest=_DIGEST, media_type=media_type
    )


def _evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact("m2504.evidence"),
            role="evidence",
            claim="Caller-declared external transport evidence.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.5,
        rationale="Caller-declared transport uncertainty.",
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


def _context(request_id: str) -> ExecutionContext:
    evidence = _artifact("m2504.control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=_VERSION,
            evidence=evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2504.contract-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2504.configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2504.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=_VERSION,
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=decision("m2504.provenance"),
            consent=ConsentReference(
                decision_id="m2504.consent",
                state=ConsentState.GRANTED,
                policy_version=_VERSION,
                evidence=evidence,
            ),
            quality=decision("m2504.quality"),
            support=decision("m2504.support"),
            intended_use=decision("m2504.intended-use"),
        ),
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
        provenance_artifact=_artifact(f"m2504.provenance.{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=_evidence(),
    )


def _evaluation(dimension: TransportDimension) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"m2504.evaluation.{dimension.value}",
        dimension=dimension,
        status=TransportStatus.SUPPORTED,
        metric_name="balanced_transport_score",
        metric_value=0.9,
        calibration_floor=0.8,
        rationale="Caller-declared external validation clears the floor.",
        evidence=_evidence(),
    )


def build_request() -> EvaluateProteotypeExternalTransportRequest:
    request_id = "m2504.contract-request"
    benchmark = _artifact("m2503.benchmark", M2504_M2503_INPUT_MEDIA_TYPE)
    return EvaluateProteotypeExternalTransportRequest(
        request_id=request_id,
        context=_context(request_id),
        mass_spectrometry_proteome=_artifact("m2504.proteome"),
        genome_transcriptome=_artifact("m2504.genome-transcriptome"),
        ptm_annotations=_artifact("m2504.ptm"),
        benchmark_package=benchmark,
        validations=tuple(_validation(dimension) for dimension in _DIMENSIONS),
        evaluations=tuple(_evaluation(dimension) for dimension in _DIMENSIONS),
        configuration=TransportConfiguration(
            configuration_id="m2504.configuration",
            version=_VERSION,
            required_dimensions=_DIMENSIONS,
            minimum_calibration_floor=0.8,
            evidence=_evidence(),
        ),
        source_artifacts=(benchmark, _artifact("m2504.policy")),
    )


def test_request_closes_all_seven_transport_dimensions() -> None:
    request = build_request()
    assert {item.dimension for item in request.validations} == set(_DIMENSIONS)
    assert {item.dimension for item in request.evaluations} == set(_DIMENSIONS)
    assert request.configuration.locked is True


def test_unknown_request_field_is_rejected() -> None:
    data = build_request().model_dump(mode="python")
    data["unexpected"] = "hostile"
    with pytest.raises(ValidationError):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_wrong_upstream_media_is_rejected() -> None:
    data = build_request().model_dump(mode="python")
    data["benchmark_package"] = _artifact("m2503.benchmark", "application/json")
    with pytest.raises(ValidationError, match="M25-03"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_duplicate_validation_dimensions_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["validations"] = (request.validations[0], request.validations[0], *request.validations[2:])
    with pytest.raises(ValidationError, match="validation dimensions"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_duplicate_source_artifacts_are_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["source_artifacts"] = (request.source_artifacts[0], request.source_artifacts[0])
    with pytest.raises(ValidationError, match="source artifact"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_missing_benchmark_source_binding_is_rejected() -> None:
    request = build_request()
    data = request.model_dump(mode="python")
    data["source_artifacts"] = (_artifact("m2504.policy"),)
    with pytest.raises(ValidationError, match="benchmark package"):
        EvaluateProteotypeExternalTransportRequest.model_validate(data, strict=True)


def test_support_domain_must_account_for_all_dimensions() -> None:
    with pytest.raises(ValidationError, match="all seven"):
        SupportDomainUpdate(
            update_id="m2504.update",
            version=_VERSION,
            status=TransportStatus.SUPPORTED,
            retained_dimensions=(TransportDimension.SITE,),
            rationale="Incomplete support declaration.",
            evidence=_evidence(),
        )


def test_failed_calibration_cannot_be_marked_supported() -> None:
    with pytest.raises(ValidationError, match="calibration floor"):
        TransportEvaluation(
            evaluation_id="m2504.bad-evaluation",
            dimension=TransportDimension.SITE,
            status=TransportStatus.SUPPORTED,
            metric_name="score",
            metric_value=0.4,
            calibration_floor=0.8,
            rationale="Contradictory support claim.",
            evidence=_evidence(),
        )
