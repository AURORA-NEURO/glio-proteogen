"""Deterministic M03-01 protein-inference protocol conformance evaluator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_01.canonical import (
    canonical_request_digest,
    configuration_digest,
    normalized_request,
    profile_digest,
    protocol_digest,
    protocol_section_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_01.v1 import (
    M0301_CONFORMANT_SUPPORT_RATIONALE,
    M0301_CONTRACT_VERSION,
    M0301_MODULE_ID,
    M0301_QUARANTINED_SUPPORT_RATIONALE,
    M0301_SENSITIVITY_NOTES,
    M0301_UNCERTAINTY_RATIONALES,
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceProtocolReceipt,
    ProtocolConformanceDisposition,
    ProtocolConformanceFinding,
    ProtocolConformanceStatus,
    ProtocolFindingState,
    expected_protocol_findings,
    protocol_evidence_index,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinInferenceProtocolRequest)
_AUTHORIZATION_MESSAGE: Final = (
    "protein-inference protocol evaluation requires accepted upstream controls"
)
_LIMITATIONS: Final = (
    Limitation(
        code="protocol_conformance_only",
        statement=(
            "This result validates a declared protein-inference protocol against one reviewed "
            "profile; it does not search spectra, assign peptides, infer proteins, or estimate "
            "error rates."
        ),
    ),
    Limitation(
        code="complex_activity_not_inferred",
        statement=(
            "The complex-activity handoff contains protocol receipts and preserved ambiguity "
            "only; no complex, kinase, subtype, treatment, or clinical claim is produced."
        ),
    ),
)


class ProteinInferenceProtocolAuthorizationError(ValueError):
    """Authorization failed before a protocol or profile was traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M0301ProteinInferenceProtocolEngine:
    """Evaluate reviewed protocol closure without executing protein inference."""

    __slots__ = ()

    def evaluate(self, request: object) -> ProteinInferenceProtocolConformanceResult:
        preflight_protein_inference_protocol_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        findings = _findings(canonical)
        status = _status(findings)
        disposition = (
            ProtocolConformanceDisposition.CONFORMANT
            if status is ProtocolConformanceStatus.CONFORMANT
            else ProtocolConformanceDisposition.QUARANTINED
        )
        request_hash = canonical_request_digest(canonical)
        protocol_hash = protocol_digest(canonical.protocol_schema)
        active_profile_hash = profile_digest(canonical.conformance_profile)
        configuration_hash = configuration_digest(
            canonical.protocol_schema,
            canonical.conformance_profile,
        )
        receipt = _receipt(
            canonical,
            disposition,
            protocol_hash,
            active_profile_hash,
            configuration_hash,
        )
        payload = {
            "output_type": "protein_inference_protocol_conformance_result",
            "result_id": f"result.m0301.{request_hash.removeprefix('sha256:')}",
            "result_version": M0301_CONTRACT_VERSION,
            "request_digest": request_hash,
            "protocol_digest": protocol_hash,
            "profile_digest": active_profile_hash,
            "configuration_digest": configuration_hash,
            "result_digest": "sha256:" + ("0" * 64),
            "context": canonical.context,
            "protocol_schema": canonical.protocol_schema,
            "conformance_profile": canonical.conformance_profile,
            "receipt": receipt,
            "findings": findings,
            "status": status,
            "disposition": disposition,
            "parent_target": "complex_activity",
            "infers_protein": False,
            "infers_proteoform": False,
            "infers_isoform": False,
            "infers_glioma_specific_biology": False,
            "support": _support(disposition),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(
                canonical,
                (
                    request_hash,
                    protocol_hash,
                    active_profile_hash,
                    configuration_hash,
                ),
                receipt,
            ),
            "evidence": protocol_evidence_index(canonical),
            "limitations": _LIMITATIONS,
            "human_review_required": disposition
            is ProtocolConformanceDisposition.QUARANTINED,
            "completed_at": canonical.context.occurred_at,
            "supersedes_result_digest": canonical.supersedes_result_digest,
        }
        materialized = cast(
            "dict[str, Any]",
            strict_json_loads(canonical_json_bytes(payload)),
        )
        payload["result_digest"] = result_payload_digest(materialized)
        return ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def evaluate_protein_inference_protocol(
    request: object,
) -> ProteinInferenceProtocolConformanceResult:
    """Public stateless protocol-conformance entry point."""

    return M0301ProteinInferenceProtocolEngine().evaluate(request)


def preflight_protein_inference_protocol_authorization(candidate: object) -> None:
    """Reject denied controls before reading protocol or conformance-profile payloads."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, EvaluateProteinInferenceProtocolRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        authorized = all(
            _member(_member(references, role), "state") == state
            for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - fail closed at the hostile mapping boundary.
        raise ProteinInferenceProtocolAuthorizationError from None
    if not authorized:
        raise ProteinInferenceProtocolAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _findings(
    request: EvaluateProteinInferenceProtocolRequest,
) -> tuple[ProtocolConformanceFinding, ...]:
    return tuple(
        sorted(
            expected_protocol_findings(
                request.protocol_schema,
                request.conformance_profile,
            ),
            key=canonical_json_bytes,
        )
    )


def _status(
    findings: tuple[ProtocolConformanceFinding, ...],
) -> ProtocolConformanceStatus:
    states = {item.state for item in findings}
    if ProtocolFindingState.FAIL in states:
        return ProtocolConformanceStatus.NONCONFORMANT
    if ProtocolFindingState.NOT_EVALUABLE in states:
        return ProtocolConformanceStatus.INDETERMINATE
    return ProtocolConformanceStatus.CONFORMANT


def _receipt(
    request: EvaluateProteinInferenceProtocolRequest,
    disposition: ProtocolConformanceDisposition,
    protocol_hash: str,
    active_profile_hash: str,
    configuration_hash: str,
) -> ProteinInferenceProtocolReceipt:
    protocol = request.protocol_schema
    return ProteinInferenceProtocolReceipt(
        protocol_digest=protocol_hash,
        profile_digest=active_profile_hash,
        configuration_digest=configuration_hash,
        search_space_digest=protocol_section_digest(protocol, "search_space"),
        error_control_digest=protocol_section_digest(protocol, "error_control"),
        assignment_digest=protocol_section_digest(protocol, "assignment"),
        protein_group_digest=protocol_section_digest(protocol, "protein_grouping"),
        ambiguity_digest=protocol_section_digest(protocol, "ambiguity"),
        handoff_digest=protocol_section_digest(protocol, "complex_activity_handoff"),
        identity_subject_digest=request.context.references.identity_lineage.binding_digest,
        intended_use_evidence_digest=request.context.references.intended_use.evidence.digest,
        disposition=disposition,
    )


def _support(disposition: ProtocolConformanceDisposition) -> SupportDecision:
    if disposition is ProtocolConformanceDisposition.CONFORMANT:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="protein_inference_protocol_conformant",
            rationale=M0301_CONFORMANT_SUPPORT_RATIONALE,
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="protein_inference_protocol_quarantined",
        rationale=M0301_QUARANTINED_SUPPORT_RATIONALE,
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable(M0301_UNCERTAINTY_RATIONALES[0]),
        sampling=unavailable(M0301_UNCERTAINTY_RATIONALES[1]),
        parameter=unavailable(M0301_UNCERTAINTY_RATIONALES[2]),
        model_form=unavailable(M0301_UNCERTAINTY_RATIONALES[3]),
        identification=unavailable(M0301_UNCERTAINTY_RATIONALES[4]),
        support=unavailable(M0301_UNCERTAINTY_RATIONALES[5]),
        transport=unavailable(M0301_UNCERTAINTY_RATIONALES[6]),
        sensitivity_notes=M0301_SENSITIVITY_NOTES,
    )


def _controls(
    request: EvaluateProteinInferenceProtocolRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _provenance(
    request: EvaluateProteinInferenceProtocolRequest,
    hashes: tuple[str, str, str, str],
    receipt: ProteinInferenceProtocolReceipt,
) -> ProvenanceRecord:
    request_hash, protocol_hash, active_profile_hash, configuration_hash = hashes
    references = request.context.references
    controls = _controls(request)
    return ProvenanceRecord(
        activity_id=f"activity.m0301.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0301_MODULE_ID,
        module_version=M0301_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_hash,
                    protocol_hash,
                    active_profile_hash,
                    configuration_hash,
                    receipt.search_space_digest,
                    receipt.error_control_digest,
                    receipt.assignment_digest,
                    receipt.protein_group_digest,
                    receipt.ambiguity_digest,
                    receipt.handoff_digest,
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M0301ProteinInferenceProtocolEngine",
    "ProteinInferenceProtocolAuthorizationError",
    "evaluate_protein_inference_protocol",
    "preflight_protein_inference_protocol_authorization",
]
