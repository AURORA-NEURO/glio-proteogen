"""Adversarial closure for the provisional M20-07 export contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_07 import (
    M2007_M2006_INPUT_MEDIA_TYPE,
    M2007_MODULE_ID,
    CompatibilityMode,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportField,
    ExportFieldType,
    ExportFinding,
    ExportFindingCode,
    ExportOwnershipBinding,
    ExportProteinSubtypeDownstreamContractRequest,
    ExportStatus,
    ProteinSubtypeDownstreamExportResult,
    SignedContractEnvelope,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2007.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2007:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-07 export evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2007.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m2007.synthetic",
        actor_id="actor.m2007.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2007.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2007.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2007.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _field(name: str = "protein_subtype") -> ExportField:
    artifact = _artifact(f"field-{name}")
    return ExportField(
        field_id=f"field.m2007.{name}",
        field_name=name,
        value_type=ExportFieldType.ENUM,
        field_version="1.0.0",
        owner="Computational biology",
        documentation="Documented protein subtype downstream field.",
        value_digest=sha256_digest(f"value:{name}"),
        evidence=(_evidence(artifact),),
    )


def _configuration() -> DownstreamExportConfiguration:
    return DownstreamExportConfiguration(
        configuration_id="configuration.m2007.synthetic",
        version="1.0.0",
        compatibility=CompatibilityMode.VERSIONED,
        evidence=(_evidence(_artifact("configuration-export")),),
    )


def _request() -> ExportProteinSubtypeDownstreamContractRequest:
    upstream = _artifact("upstream", M2007_M2006_INPUT_MEDIA_TYPE)
    return ExportProteinSubtypeDownstreamContractRequest(
        request_id="request.m2007.synthetic",
        context=_context(),
        upstream_result=upstream,
        fields=(_field(),),
        consent=_context().references.consent,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="synthetic_support",
            rationale="Caller-declared upstream support is accepted for export.",
        ),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("field-protein_subtype")),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M20-07 exports declared fields and does not estimate biological truth.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Export is sensitive to declared support, consent, compatibility and ownership.",
        ),
    )


def _provenance(request: ExportProteinSubtypeDownstreamContractRequest) -> ProvenanceRecord:
    refs = request.context.references
    records = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2007_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=records,
    )


def _result() -> ProteinSubtypeDownstreamExportResult:
    request = _request()
    evidence = (_evidence(request.upstream_result), _evidence(_artifact("result-proof")))
    ownership = ExportOwnershipBinding(
        owning_module=M2007_MODULE_ID,
        owner="Computational biology",
        ownership_statement="M20-07 owns this bounded downstream export object.",
        evidence=(_evidence(_artifact("ownership")),),
    )
    signature = SignedContractEnvelope(
        signer_id="signer.m2007.synthetic",
        algorithm="external-signature-declaration",
        signed_payload_digest=sha256_digest("signed-payload"),
        signature_digest=sha256_digest("signature"),
        evidence=(_evidence(_artifact("signature")),),
    )
    contract = DownstreamContractObject(
        contract_id="contract.m2007.synthetic",
        version="1.0.0",
        fields=request.fields,
        ownership=ownership,
        consent=request.consent,
        support_decision=request.support_decision,
        configuration=request.configuration,
        signature=signature,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
    )
    payload: dict[str, Any] = {
        "result_id": f"result.{canonical_request_digest(request).removeprefix('sha256:')}",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": ExportStatus.EXPORTED,
        "contract": contract,
        "support_decision": request.support_decision,
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": evidence,
        "limitations": (),
        "human_review_required": False,
    }
    payload["limitations"] = (
        Limitation(
            code="provisional", statement="ABI remains provisional pending owner confirmation."
        ),
    )
    payload["result_digest"] = result_payload_digest(
        ProteinSubtypeDownstreamExportResult.model_construct(
            output_type="protein_subtype_downstream_contract",
            parent_target="protein subtype",
            emits_parent=False,
            findings=(),
            abstention_reason=None,
            **payload,
        )
    )
    return TypeAdapter(ProteinSubtypeDownstreamExportResult).validate_python(
        ProteinSubtypeDownstreamExportResult.model_construct(
            output_type="protein_subtype_downstream_contract",
            parent_target="protein subtype",
            emits_parent=False,
            findings=(),
            abstention_reason=None,
            **payload,
        ),
        strict=True,
    )


def test_request_requires_m20_06_media_and_unique_sources() -> None:
    with pytest.raises(ValidationError, match="M20-06"):
        TypeAdapter(ExportProteinSubtypeDownstreamContractRequest).validate_python(
            _request().model_copy(update={"upstream_result": _artifact("wrong")}),
            strict=True,
        )
    request = _request()
    with pytest.raises(ValidationError, match="source artifact ids"):
        TypeAdapter(ExportProteinSubtypeDownstreamContractRequest).validate_python(
            request.model_copy(update={"source_artifacts": (request.source_artifacts[0],) * 2}),
            strict=True,
        )


def test_request_export_fields_and_evidence_collections_are_closed() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="field ids"):
        TypeAdapter(ExportProteinSubtypeDownstreamContractRequest).validate_python(
            request.model_copy(update={"fields": (request.fields[0], request.fields[0])}),
            strict=True,
        )
    field = _field()
    with pytest.raises(ValidationError, match="field evidence"):
        ExportField.model_validate(
            field.model_dump() | {"evidence": field.evidence + field.evidence}
        )


def test_configuration_and_signature_must_be_locked_and_unique() -> None:
    configuration = _configuration()
    with pytest.raises(ValidationError, match="immutable"):
        DownstreamExportConfiguration.model_validate(
            configuration.model_dump() | {"immutable": False}
        )
    signature = SignedContractEnvelope(
        signer_id="signer.m2007.synthetic",
        algorithm="external-signature-declaration",
        signed_payload_digest=sha256_digest("signed-payload"),
        signature_digest=sha256_digest("signature"),
        evidence=(_evidence(_artifact("signature")),),
    )
    with pytest.raises(ValidationError, match="signature evidence"):
        SignedContractEnvelope.model_validate(
            signature.model_dump() | {"evidence": signature.evidence + signature.evidence}
        )


def test_result_identity_replay_and_status_closures_are_explicit() -> None:
    result = _result()
    assert result.result_id.removeprefix("result.") == result.request_digest.removeprefix("sha256:")
    payload = result.model_dump()
    with pytest.raises(ValidationError, match="result identifier"):
        TypeAdapter(ProteinSubtypeDownstreamExportResult).validate_python(
            payload | {"result_id": "result.tampered"}, strict=True
        )
    finding = ExportFinding(
        finding_id="finding.m2007.duplicate",
        code=ExportFindingCode.FIELD_UNDOCUMENTED,
        message="A field is not documented.",
    )
    with pytest.raises(ValidationError, match="finding ids"):
        TypeAdapter(ProteinSubtypeDownstreamExportResult).validate_python(
            payload | {"findings": (finding, finding)}, strict=True
        )
    abstained = payload | {
        "status": ExportStatus.ABSTAINED,
        "contract": None,
        "abstention_reason": "Review required.",
        "support_decision": SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="review_required",
            rationale="Review is required before export.",
        ),
        "human_review_required": False,
    }
    with pytest.raises(ValidationError, match="abstained result"):
        TypeAdapter(ProteinSubtypeDownstreamExportResult).validate_python(abstained, strict=True)


def test_contract_object_rejects_wrong_ownership_binding() -> None:
    result = _result()
    assert result.contract is not None
    tampered_contract = result.contract.model_copy(
        update={
            "ownership": result.contract.ownership.model_copy(
                update={"owning_module": "GLIO-PROTEOGEN-M20-06"}
            )
        }
    )
    with pytest.raises(ValidationError, match="ownership binding"):
        TypeAdapter(ProteinSubtypeDownstreamExportResult).validate_python(
            result.model_copy(update={"contract": tampered_contract}),
            strict=True,
        )
