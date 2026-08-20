"""Adversarial request and evaluated-report closure coverage for M25-04."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from glio_proteogen.contracts.m25_04 import (
    EvaluateProteotypeExternalTransportRequest,
    EvaluationStatus,
    ProteotypeExternalTransportResult,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2504.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2504:{name}"),
        media_type="application/json",
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name), role="evidence", claim="M25-04 caller evidence."
    )


def _context(request_id: str = "request.m2504.transport") -> ExecutionContext:
    control = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2504.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=control,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2504.transport",
        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2504.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2504.identity"),
                evidence=control,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2504.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=control,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M25-04 transport fixture does not estimate uncertainty.",
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


def _configuration() -> TransportConfiguration:
    return TransportConfiguration(
        configuration_id="configuration.m2504.transport",
        version="1.0.0",
        required_dimensions=(TransportDimension.SITE,),
        minimum_calibration_floor=0.8,
        evidence=(_evidence("configuration"),),
    )


def _validation() -> TransportValidation:
    return TransportValidation(
        validation_id="validation.m2504.site",
        dimension=TransportDimension.SITE,
        source_domain="source-site",
        target_domain="target-site",
        assay_or_platform="platform-a",
        specimen_description="specimen-a",
        sample_count=4,
        provenance_artifact=_artifact("validation-provenance"),
        uncertainty=_uncertainty(),
        evidence=(_evidence("validation"),),
    )


def _evaluation() -> TransportEvaluation:
    return TransportEvaluation(
        evaluation_id="evaluation.m2504.site",
        dimension=TransportDimension.SITE,
        status=TransportStatus.SUPPORTED,
        metric_name="calibration",
        metric_value=0.9,
        calibration_floor=0.8,
        rationale="Fixture meets the declared calibration floor.",
        evidence=(_evidence("evaluation"),),
    )


def _report() -> TransportabilityReport:
    return TransportabilityReport(
        report_id="report.m2504.transport",
        version="1.0.0",
        validations=(_validation(),),
        evaluations=(_evaluation(),),
        support_domain=SupportDomainUpdate(
            update_id="support.m2504.transport",
            version="1.0.0",
            status=TransportStatus.SUPPORTED,
            retained_dimensions=(TransportDimension.SITE,),
            rationale="Fixture retains the supported transport dimension.",
            evidence=(_evidence("support-domain"),),
        ),
        configuration=_configuration(),
        evidence=(_evidence("report"),),
    )


def _request() -> EvaluateProteotypeExternalTransportRequest:
    return EvaluateProteotypeExternalTransportRequest(
        request_id="request.m2504.transport",
        context=_context(),
        mass_spectrometry_proteome=_artifact("proteome"),
        genome_transcriptome=_artifact("genome"),
        ptm_annotations=_artifact("ptm"),
        benchmark_package=_artifact("benchmark"),
        validations=(_validation(),),
        evaluations=(_evaluation(),),
        configuration=_configuration(),
        source_artifacts=(
            _artifact("proteome"),
            _artifact("genome"),
            _artifact("ptm"),
            _artifact("benchmark"),
        ),
    )


def _result() -> ProteotypeExternalTransportResult:
    request = _request()
    payload: dict[str, Any] = {
        "output_type": "proteotype_external_transport",
        "result_id": "result.m2504.transport",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + ("0" * 64),
        "request": request,
        "status": EvaluationStatus.EVALUATED,
        "report": _report(),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "proteotype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m2504_transport_supported",
            rationale="The locked transport fixture is supported.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": ProvenanceRecord(
            activity_id="activity.m2504.transport",
            actor_id=request.context.actor_id,
            module_id="GLIO-PROTEOGEN-M25-04",
            module_version="0.1.0-provisional",
            generated_at=request.context.occurred_at,
            input_digests=tuple(item.digest for item in request.source_artifacts),
            configuration_digest=_artifact("configuration").digest,
            consent_decision_id=request.context.references.consent.decision_id,
            consent_state=request.context.references.consent.state,
            consent_policy_version=request.context.references.consent.policy_version,
            consent_evidence_digest=request.context.references.consent.evidence.digest,
            control_decisions=tuple(
                ControlDecisionRecord(
                    role=role,
                    decision_id=f"decision.m2504.{role.value}",
                    state=(
                        IdentityLineageState.RESOLVED.value
                        if role is ControlRole.IDENTITY_LINEAGE
                        else (
                            ConsentState.GRANTED.value
                            if role is ControlRole.CONSENT
                            else UpstreamDecisionState.ACCEPTED.value
                        )
                    ),
                    policy_version="1.0.0",
                    evidence_digest=_artifact("control").digest,
                    subject_digest=(
                        sha256_digest("m2504.identity")
                        if role is ControlRole.IDENTITY_LINEAGE
                        else None
                    ),
                )
                for role in ControlRole
            ),
        ),
        "evidence": (_evidence("result"),),
        "limitations": (
            Limitation(code="m2504_provisional", statement="The M25-04 ABI is provisional."),
        ),
        "human_review_required": True,
    }
    constructed = ProteotypeExternalTransportResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(constructed)
    return ProteotypeExternalTransportResult.model_validate(payload)


def test_request_context_and_source_manifest_are_closed() -> None:
    request = _request()
    changed = request.model_dump(mode="python")
    changed["context"] = _context("request.m2504.other")
    with pytest.raises(ValueError, match="context must bind"):
        EvaluateProteotypeExternalTransportRequest.model_validate(changed)

    changed = request.model_dump(mode="python")
    changed["source_artifacts"] = request.source_artifacts[:-1]
    with pytest.raises(ValueError, match="every declared transport input"):
        EvaluateProteotypeExternalTransportRequest.model_validate(changed)


def test_evaluated_result_rejects_self_rehashed_report_declaration_mutation() -> None:
    result = _result()
    assert result.report is not None
    forged_validation = result.report.validations[0].model_copy(
        update={"source_domain": "forged-source-domain"}
    )
    forged_report = result.report.model_copy(
        update={"validations": (forged_validation, *result.report.validations[1:])}
    )
    forged = result.model_copy(update={"report": forged_report})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request declarations"):
        ProteotypeExternalTransportResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )
