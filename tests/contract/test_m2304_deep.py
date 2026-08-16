"""Deep contract, source-binding, support-domain, and replay tests for M23-04."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m23_04 import (
    M2304_DOSSIER_SHA256,
    M2304_DOSSIER_SLICE,
    EvaluateVariantPeptideExternalTransportRequest,
    EvaluationStatus,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
    VariantPeptideExternalTransportResult,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_DIMENSIONS = tuple(TransportDimension)
_SCHEMA_COUNT = 8


def _artifact(label: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2304.{label}",
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(label: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M23-04 transport evidence.",
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.5,
        rationale="Caller-declared transport uncertainty; no biological estimate is inferred.",
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


def _decision(role: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"m2304.{role}.decision",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="0.1.0",
        evidence=_artifact(f"{role}-decision"),
    )


def _context(request_id: str = "request-1") -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2304.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2304.identity.decision",
                state=IdentityLineageState.RESOLVED,
                policy_version="0.1.0",
                binding_digest=_artifact("identity-binding").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="m2304.consent.decision",
                state=ConsentState.GRANTED,
                policy_version="0.1.0",
                evidence=_artifact("consent-evidence"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _validation(dimension: TransportDimension) -> TransportValidation:
    return TransportValidation(
        validation_id=f"validation-{dimension.value}",
        dimension=dimension,
        source_domain=f"source-{dimension.value}",
        target_domain=f"target-{dimension.value}",
        assay_or_platform="cross-instrument quantitative assay",
        specimen_description="Caller-declared frozen glioma specimen",
        sample_count=12,
        provenance_artifact=_artifact(f"{dimension.value}-provenance"),
        uncertainty=_uncertainty(),
        evidence=(_evidence(f"{dimension.value}-validation"),),
    )


def _evaluation(dimension: TransportDimension) -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id=f"evaluation-{dimension.value}",
        dimension=dimension,
        status=TransportStatus.SUPPORTED,
        metric_name="transport_calibration",
        metric_value=0.9,
        calibration_floor=0.8,
        rationale="Independent caller-declared transport validation meets the floor.",
        evidence=(_evidence(f"{dimension.value}-evaluation"),),
    )


def _configuration() -> TransportConfiguration:
    return TransportConfiguration(
        configuration_id="configuration-1",
        version="0.1.0",
        required_dimensions=_DIMENSIONS,
        minimum_calibration_floor=0.8,
        evidence=(_evidence("configuration"),),
    )


def _request(request_id: str = "request-1") -> EvaluateVariantPeptideExternalTransportRequest:
    inputs = (
        _artifact("mass-spectrometry-proteome"),
        _artifact("genome-transcriptome"),
        _artifact("ptm-annotations"),
        _artifact("benchmark-package"),
    )
    return EvaluateVariantPeptideExternalTransportRequest(
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


def _report(request: EvaluateVariantPeptideExternalTransportRequest) -> TransportabilityReport:
    return TransportabilityReport(
        report_id="report-1",
        version="0.1.0",
        validations=request.validations,
        evaluations=request.evaluations,
        support_domain=SupportDomainUpdate(
            update_id="support-update-1",
            version="0.1.0",
            status=TransportStatus.SUPPORTED,
            retained_dimensions=_DIMENSIONS,
            rationale="All configured dimensions meet the declared calibration floor.",
            evidence=(_evidence("support-domain"),),
        ),
        configuration=request.configuration,
        evidence=(_evidence("report"),),
    )


def _provenance(request: EvaluateVariantPeptideExternalTransportRequest) -> ProvenanceRecord:
    digest = request.source_artifacts[0].digest
    references = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return ProvenanceRecord(
        activity_id="m2304.activity-1",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M23-04",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=str(decision.state.value),
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=(
                    decision.binding_digest
                    if isinstance(decision, IdentityLineageReference)
                    else None
                ),
            )
            for role, decision in decisions
        ),
    )


def _result(
    request: EvaluateVariantPeptideExternalTransportRequest,
) -> VariantPeptideExternalTransportResult:
    request_digest = canonical_request_digest(request)
    base: dict[str, Any] = {
        "result_id": result_identifier(request_digest),
        "request_digest": request_digest,
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": EvaluationStatus.EVALUATED,
        "report": _report(request),
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="transport_supported",
            rationale="All seven transport dimensions meet the configured floor.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "limitations": (
            Limitation(
                code="caller_declared_transport",
                statement="Issuer authority and laboratory execution are not authenticated.",
            ),
        ),
        "human_review_required": True,
    }
    provisional = VariantPeptideExternalTransportResult.model_construct(**cast("Any", base))
    base["result_digest"] = result_payload_digest(provisional)
    return VariantPeptideExternalTransportResult.model_validate(base, strict=True)


def test_authority_schema_and_transport_dimensions_are_locked() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert M2304_DOSSIER_SHA256.startswith("sha256:")
    assert M2304_DOSSIER_SLICE.endswith(":8088-8128")
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "variant peptide"
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["dossierSha256"] == M2304_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert set(_DIMENSIONS) == {
        TransportDimension.SITE,
        TransportDimension.LAB,
        TransportDimension.PLATFORM,
        TransportDimension.TREATMENT_ERA,
        TransportDimension.POPULATION,
        TransportDimension.DISEASE_CLASS,
        TransportDimension.SPECIMEN,
    }


def test_request_and_result_replay_bind_exact_artifacts_and_ids() -> None:
    request = _request()
    result = _result(request)
    assert result.result_id == result_identifier(canonical_request_digest(request))
    assert result.result_digest == result_payload_digest(result)
    with pytest.raises(ValidationError, match="source artifacts"):
        EvaluateVariantPeptideExternalTransportRequest.model_validate(
            request.model_copy(
                update={"source_artifacts": (request.source_artifacts[0],)}
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="result identifier"):
        VariantPeptideExternalTransportResult.model_validate(
            result.model_copy(update={"result_id": "tampered"}).model_dump()
        )
    with pytest.raises(ValidationError, match="result digest"):
        VariantPeptideExternalTransportResult.model_validate(
            result.model_copy(update={"result_digest": "sha256:" + "f" * 64}).model_dump()
        )


def test_request_context_and_dimension_closure_reject_substitution() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="execution context"):
        EvaluateVariantPeptideExternalTransportRequest.model_validate(
            request.model_copy(update={"context": _context("different")}).model_dump()
        )
    with pytest.raises(ValidationError, match="validation dimensions"):
        EvaluateVariantPeptideExternalTransportRequest.model_validate(
            request.model_copy(
                update={"validations": (*request.validations, request.validations[0])}
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="unique"):
        TransportConfiguration.model_validate(
            _configuration().model_copy(
                update={"required_dimensions": (_DIMENSIONS[0], _DIMENSIONS[0])}
            ).model_dump()
        )


def test_transport_status_and_support_domain_boundaries_are_explicit() -> None:
    with pytest.raises(ValidationError, match="calibration floor"):
        _evaluation(TransportDimension.SITE).model_copy(
            update={"metric_value": 0.7, "status": TransportStatus.SUPPORTED}
        ).__class__.model_validate(
            _evaluation(TransportDimension.SITE).model_dump()
            | {"metric_value": 0.7, "status": TransportStatus.SUPPORTED}
        )
    request = _request()
    report = _report(request)
    with pytest.raises(ValidationError, match="supported report"):
        TransportabilityReport.model_validate(
            report.model_copy(
                update={
                    "support_domain": report.support_domain.model_copy(
                        update={
                            "retained_dimensions": _DIMENSIONS[1:],
                            "narrowed_dimensions": (_DIMENSIONS[0],),
                        }
                    )
                }
            ).model_dump()
        )
