"""Adversarial contract closure for provisional M21-04."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m21_04 import (
    M2104_DOSSIER_SHA256,
    M2104_DOSSIER_SLICE,
    M2104_M2103_INPUT_MEDIA_TYPE,
    EvaluateComplexActivityExternalTransportRequest,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import sha256_digest
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

DIMENSIONS = tuple(TransportDimension)


def _artifact(
    name: str, media_type: str = "application/vnd.glio-proteogen.evidence+json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2104.{name}",
        version="1.0.0",
        digest=sha256_digest({"m2104": name, "media": media_type}),
        media_type=media_type,
    )


def _evidence(name: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(name),
            role="evidence",
            claim="Caller-declared M21-04 transport evidence.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.9,
        rationale="Caller-declared transport uncertainty estimate.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Transport issuer authority remains caller-declared.",),
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2104.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        name: _artifact(f"control-{name}")
        for name in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m2104.synthetic",
        actor_id="actor.m2104.synthetic",
        occurred_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2104.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2104.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2104.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended"]),
        ),
    )


def _config() -> TransportConfiguration:
    return TransportConfiguration(
        configuration_id="configuration.m2104.synthetic",
        version="1.0.0",
        required_dimensions=DIMENSIONS,
        minimum_calibration_floor=0.8,
        evidence=_evidence("configuration"),
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"validation.m2104.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="proteome-platform",
        specimen_description="frozen specimen",
        sample_count=12,
        provenance_artifact=_artifact(f"provenance-{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=_evidence(f"validation-{dimension.value}"),
    )


def _evaluation(
    dimension: TransportDimension,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> TransportEvaluation:
    floor = 0.8
    value = 0.9 if status is TransportStatus.SUPPORTED else 0.5
    return TransportEvaluation(
        evaluation_id=f"evaluation.m2104.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport calibration",
        metric_value=value,
        calibration_floor=floor,
        rationale="Caller-declared external transport evaluation.",
        evidence=_evidence(f"evaluation-{dimension.value}"),
    )


def _request(
    *,
    benchmark_media_type: str = M2104_M2103_INPUT_MEDIA_TYPE,
    evaluations: tuple[TransportEvaluation, ...] | None = None,
) -> EvaluateComplexActivityExternalTransportRequest:
    benchmark = _artifact("benchmark", benchmark_media_type)
    return EvaluateComplexActivityExternalTransportRequest(
        request_id="request.m2104.synthetic",
        context=_context(),
        benchmark_package=benchmark,
        validations=tuple(_validation(dimension) for dimension in DIMENSIONS),
        evaluations=evaluations or tuple(_evaluation(dimension) for dimension in DIMENSIONS),
        configuration=_config(),
        source_artifacts=(benchmark, _artifact("source")),
    )


def _report(request: EvaluateComplexActivityExternalTransportRequest) -> TransportabilityReport:
    return TransportabilityReport(
        report_id="report.m2104.synthetic",
        version=request.configuration.version,
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id="support.m2104.synthetic",
            version=request.configuration.version,
            status=TransportStatus.SUPPORTED,
            retained_dimensions=DIMENSIONS,
            rationale="All configured transport dimensions remain supported.",
            evidence=_evidence("support-domain"),
        ),
        configuration=request.configuration,
        evidence=_evidence("report"),
    )


def test_authority_media_and_schema_metadata_are_explicit() -> None:
    assert (
        M2104_DOSSIER_SHA256
        == "sha256:" + "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2104_DOSSIER_SLICE.endswith(":7368-7408")
    schema = cast("dict[str, Any]", contract_json_schema("request"))
    metadata = schema["x-glio-contract"]
    assert metadata["dossierSha256"] == M2104_DOSSIER_SHA256
    assert metadata["upstreamInputMediaType"] == M2104_M2103_INPUT_MEDIA_TYPE


def test_request_and_report_close_all_seven_dimensions() -> None:
    request = _request()
    report = _report(request)
    assert {item.dimension for item in report.validations} == set(DIMENSIONS)
    assert {item.dimension for item in report.evaluations} == set(DIMENSIONS)
    assert set(report.support_domain.retained_dimensions) == set(DIMENSIONS)


def test_status_floors_and_support_domains_are_fail_closed() -> None:
    evaluation = _evaluation(TransportDimension.SITE)
    with pytest.raises(ValidationError, match="calibration floor"):
        TransportEvaluation.model_validate(evaluation.model_copy(update={"metric_value": 0.2}))
    with pytest.raises(ValidationError, match="calibration floor"):
        TransportEvaluation.model_validate(
            evaluation.model_copy(
                update={"status": TransportStatus.DOMAIN_NARROWED, "metric_value": 0.9}
            )
        )
    with pytest.raises(ValidationError, match="disjoint"):
        SupportDomainUpdate.model_validate(
            _report(_request()).support_domain.model_copy(
                update={"narrowed_dimensions": (TransportDimension.SITE,)}
            )
        )


def test_request_rejects_wrong_upstream_and_duplicate_evaluations() -> None:
    with pytest.raises(ValidationError, match="M21-03"):
        EvaluateComplexActivityExternalTransportRequest.model_validate(
            _request(benchmark_media_type="application/json")
        )
    request = _request()
    duplicate = (*request.evaluations, request.evaluations[0])
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        EvaluateComplexActivityExternalTransportRequest.model_validate(
            request.model_copy(update={"evaluations": duplicate})
        )
