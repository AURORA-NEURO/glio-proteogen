"""Deep contract and replay closure for provisional M24-04."""

from __future__ import annotations

from datetime import UTC, datetime
from math import inf
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_04 import (
    M2404_OUTPUT_MEDIA_TYPE,
    EvaluateBiomarkerPanelExternalTransportRequest,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
    canonical_request_digest,
    contract_json_schemas,
    normalized_request,
    result_identifier,
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

_DIMENSIONS = tuple(TransportDimension)
_SCHEMA_COUNT = 8


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2404.{label}",
        version="0.1.0",
        digest="sha256:" + (label.encode().hex() + "0" * 64)[:64],
        media_type="application/json",
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared external transport evidence.",
    )


def _decision(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"m2404.{label}.decision",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="0.1.0",
        evidence=_artifact(f"{label}-decision"),
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2404.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2404.identity.decision",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_artifact("identity-binding").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="m2404.consent.decision",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact("consent-evidence"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(label: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M24-04 does not estimate {label} uncertainty from metadata.",
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
        validation_id=f"validation.{dimension.value}",
        dimension=dimension,
        source_domain="source-domain",
        target_domain="target-domain",
        assay_or_platform="validated-platform",
        specimen_description="frozen specimen",
        sample_count=10,
        provenance_artifact=_artifact(f"provenance-{dimension.value}"),
        uncertainty=_uncertainty(),
        evidence=(_evidence(f"validation-{dimension.value}"),),
    )


def _evaluation(
    dimension: TransportDimension,
    status: TransportStatus = TransportStatus.SUPPORTED,
) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"evaluation.{dimension.value}",
        dimension=dimension,
        status=status,
        metric_name="transport_calibration",
        metric_value=0.9 if status is TransportStatus.SUPPORTED else 0.4,
        calibration_floor=0.8,
        rationale="Independent validation meets the declared transport criterion."
        if status is TransportStatus.SUPPORTED
        else "Calibration floor failed; support domain is narrowed.",
        evidence=(_evidence(f"evaluation-{dimension.value}"),),
    )


def _configuration() -> TransportConfiguration:
    return TransportConfiguration(
        configuration_id="configuration.1",
        version="0.1.0",
        required_dimensions=_DIMENSIONS,
        minimum_calibration_floor=0.8,
        evidence=(_evidence("configuration"),),
    )


def _request(request_id: str = "request.1") -> EvaluateBiomarkerPanelExternalTransportRequest:
    inputs = (
        _artifact("mass-spec-proteome"),
        _artifact("genome-transcriptome"),
        _artifact("ptm-annotations"),
        _artifact("benchmark-package"),
    )
    return EvaluateBiomarkerPanelExternalTransportRequest(
        request_id=request_id,
        context=_context(request_id),
        mass_spectrometry_proteome=inputs[0],
        genome_transcriptome=inputs[1],
        ptm_annotations=inputs[2],
        benchmark_package=inputs[3],
        validations=tuple(_validation(dimension) for dimension in _DIMENSIONS),
        evaluations=tuple(_evaluation(dimension) for dimension in _DIMENSIONS),
        configuration=_configuration(),
        source_artifacts=inputs,
    )


def _report() -> TransportabilityReport:
    request = _request()
    return TransportabilityReport(
        report_id="report.1",
        version="0.1.0",
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id="support-domain.1",
            version="0.1.0",
            status=TransportStatus.SUPPORTED,
            retained_dimensions=_DIMENSIONS,
            rationale="All configured dimensions passed independent validation.",
            evidence=(_evidence("support-domain"),),
        ),
        configuration=request.configuration,
        evidence=(_evidence("report"),),
    )


def test_schema_metadata_and_replay_identity_are_explicit() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["externalTransportRequired"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        for schema in schemas.values()
    )
    request = _request()
    projected = normalized_request(request)
    assert canonical_request_digest(projected) == canonical_request_digest(request)
    assert result_identifier(projected) == result_identifier(request)
    assert M2404_OUTPUT_MEDIA_TYPE.endswith("m24-04+json")


def test_request_binds_context_and_exact_input_retention() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="execution context"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"context": _context("different")}, strict=True
        )
    with pytest.raises(ValidationError, match="exactly all declared"):
        request.__class__.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": request.source_artifacts[:-1]},
            strict=True,
        )
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (*request.source_artifacts, request.source_artifacts[0])},
            strict=True,
        )


def test_report_requires_unique_complete_dimensions() -> None:
    report = _report()
    duplicate = report.validations[0].model_copy(
        update={"dimension": report.validations[1].dimension}
    )
    with pytest.raises(ValidationError, match="validation dimensions must be unique"):
        report.__class__.model_validate(
            report.model_dump(mode="python")
            | {"validations": (duplicate, *report.validations[1:])},
            strict=True,
        )
    missing_validations = report.validations[:-1]
    with pytest.raises(ValidationError, match="every configured"):
        report.__class__.model_validate(
            report.model_dump(mode="python") | {"validations": missing_validations}, strict=True
        )
    missing = report.evaluations[:-1]
    with pytest.raises(ValidationError, match="every configured"):
        report.__class__.model_validate(
            report.model_dump(mode="python") | {"evaluations": missing}, strict=True
        )
    duplicate_evaluation = report.evaluations[0].model_copy(
        update={"dimension": report.evaluations[1].dimension}
    )
    with pytest.raises(ValidationError, match="evaluation dimensions must be unique"):
        report.__class__.model_validate(
            report.model_dump(mode="python")
            | {"evaluations": (*report.evaluations, duplicate_evaluation)},
            strict=True,
        )


def test_transport_metric_and_support_statuses_fail_closed() -> None:
    evaluation = _evaluation(TransportDimension.SITE)
    with pytest.raises(ValidationError, match="supported evaluation"):
        evaluation.__class__.model_validate(
            evaluation.model_dump(mode="python") | {"metric_value": 0.2}, strict=True
        )
    with pytest.raises(ValidationError, match="narrowed support"):
        SupportDomainUpdate(
            update_id="support-domain-bad",
            version="0.1.0",
            status=TransportStatus.DOMAIN_NARROWED,
            retained_dimensions=(TransportDimension.SITE,),
            rationale="missing narrowed dimensions",
            evidence=(_evidence("bad-support"),),
        )
    with pytest.raises(ValidationError, match=r"finite|valid number"):
        evaluation.__class__.model_validate(
            evaluation.model_dump(mode="python") | {"metric_value": inf}, strict=True
        )


def test_result_identity_changes_when_transport_evidence_changes() -> None:
    request = _request()
    changed = request.model_copy(
        update={
            "evaluations": (
                request.evaluations[0].model_copy(update={"rationale": "revised rationale"}),
                *request.evaluations[1:],
            )
        }
    )
    assert result_identifier(changed) != result_identifier(request)


def test_configuration_support_and_status_closures_reject_conflicts() -> None:
    configuration = _configuration()
    with pytest.raises(ValidationError, match="required transport dimensions"):
        configuration.__class__.model_validate(
            configuration.model_dump(mode="python")
            | {"required_dimensions": (TransportDimension.SITE, TransportDimension.SITE)},
            strict=True,
        )
    evaluation = _evaluation(TransportDimension.SITE)
    with pytest.raises(ValidationError, match="narrowed evaluation"):
        evaluation.__class__.model_validate(
            evaluation.model_dump(mode="python")
            | {"status": TransportStatus.DOMAIN_NARROWED, "metric_value": 0.9},
            strict=True,
        )
    with pytest.raises(ValidationError, match="disjoint"):
        SupportDomainUpdate(
            update_id="support-domain-overlap",
            version="0.1.0",
            status=TransportStatus.DOMAIN_NARROWED,
            retained_dimensions=(TransportDimension.SITE,),
            narrowed_dimensions=(TransportDimension.SITE,),
            rationale="overlap is unsafe",
            evidence=(_evidence("overlap"),),
        )
    with pytest.raises(ValidationError, match="supported domain"):
        SupportDomainUpdate(
            update_id="support-domain-supported-narrowed",
            version="0.1.0",
            status=TransportStatus.SUPPORTED,
            retained_dimensions=(TransportDimension.SITE,),
            narrowed_dimensions=(TransportDimension.LAB,),
            rationale="status conflict",
            evidence=(_evidence("status-conflict"),),
        )


def test_request_and_result_validation_closures_cover_replay_identity() -> None:
    request = _request()
    duplicate_validation = request.validations[0].model_copy(
        update={"dimension": request.validations[1].dimension}
    )
    with pytest.raises(ValidationError, match="request validation dimensions"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"validations": (duplicate_validation, *request.validations[1:])},
            strict=True,
        )
    duplicate_evaluation = request.evaluations[0].model_copy(
        update={"dimension": request.evaluations[1].dimension}
    )
    with pytest.raises(ValidationError, match="cover every configured"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"evaluations": (duplicate_evaluation, *request.evaluations[1:])},
            strict=True,
        )
    with pytest.raises(ValidationError, match="request evaluation dimensions"):
        request.__class__.model_validate(
            request.model_dump(mode="python")
            | {"evaluations": (*request.evaluations, duplicate_evaluation)},
            strict=True,
        )
