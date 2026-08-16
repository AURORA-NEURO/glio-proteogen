"""Replay-safe M15-02 context and subtype stratification.

The dossier leaves the scientific ABI open.  This implementation therefore
replays only caller-declared, typed context attributes and mechanism references.
It never reads source bytes, infers identity or biology, performs all-omics
fusion, emits kinase state, or recommends treatment.  Unsupported, inferred,
conflicted, and prohibited declarations abstain with an auditable envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_02 import (
    M1502_CONTRACT_VERSION,
    M1502_EVIDENCE_CLAIM,
    M1502_MODULE_ID,
    M1502_PARENT,
    ContextEvaluation,
    ContextEvaluationStatus,
    ContextFinding,
    ContextFindingCode,
    ContextProfile,
    ContextStratificationStatus,
    ContextValueStatus,
    LongitudinalRecurrenceContextStratificationResult,
    StratifyContextAndSubtypeRequest,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(StratifyContextAndSubtypeRequest)
_RESULT_ADAPTER: Final = TypeAdapter(LongitudinalRecurrenceContextStratificationResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TERMS: Final = frozenset(
    {"kinase", "kinophos", "all-omics", "all_omics", "treatment recommendation", "therapy"}
)
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source, upstream, and evidence artifacts remain immutable references; "
            "M15-02 never reads their bytes."
        ),
    ),
    Limitation(
        code="caller_declared_context",
        statement=(
            "Attributes and applicable mechanisms are replayed from typed caller "
            "declarations, not inferred from omics."
        ),
    ),
    Limitation(
        code="scientific_model_not_frozen",
        statement=(
            "No Bayesian, state-space, mechanistic, foundation, or elastic-net model "
            "executes while the ABI is provisional."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "Public operation and representation remain provisional pending Platform "
            "engineering owner confirmation."
        ),
    ),
)


class M1502AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize context stratification."""

    def __init__(self) -> None:
        super().__init__(
            "M15-02 requires accepted controls, resolved identity, and granted consent"
        )


class M1502ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-02 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-02 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1502_authorization(candidate: object) -> None:
    """Check all seven controls before traversing attributes or evidence."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1502AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1502AuthorizationError


def _as_request(candidate: object) -> StratifyContextAndSubtypeRequest:
    preflight_m1502_authorization(candidate)
    if type(candidate) is StratifyContextAndSubtypeRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(request: StratifyContextAndSubtypeRequest) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [request.upstream_result, *request.source_artifacts]
    references.extend(
        evidence.reference for attribute in request.attributes for evidence in attribute.evidence
    )
    references.extend(
        evidence.reference for mechanism in request.mechanisms for evidence in mechanism.evidence
    )
    controls = request.context.references
    references.extend(
        (
            controls.approved_configuration.evidence,
            controls.identity_lineage.evidence,
            controls.provenance.evidence,
            controls.consent.evidence,
            controls.quality.evidence,
            controls.support.evidence,
            controls.intended_use.evidence,
        )
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M1502_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(request: StratifyContextAndSubtypeRequest) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in values
    )


def _uncertainty() -> UncertaintyProfile:
    values = {
        "measurement": "Measurement values are not read from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the scientific model and public ABI open.",
        "identification": "Identity, lineage, and subtype are not inferred by this module.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": (
            "Transport across cohorts, assays, platforms, and treatment eras is not "
            "estimable."
        ),
    }
    estimate = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimate,
        sensitivity_notes=(
            "Replay stability does not imply biological or causal validity.",
            "Owner review is required before a context or subtype claim is promoted.",
        ),
    )


def _provenance(request: StratifyContextAndSubtypeRequest, request_hash: str) -> ProvenanceRecord:
    controls = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1502.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1502_MODULE_ID,
        module_version=M1502_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(
            request.context.references.approved_configuration.evidence.model_dump(mode="json")
        ),
        consent_decision_id=controls.consent.decision_id,
        consent_state=controls.consent.state,
        consent_policy_version=controls.consent.policy_version,
        consent_evidence_digest=controls.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _contains_prohibited_proxy(request: StratifyContextAndSubtypeRequest) -> bool:
    values = [
        *(item.value for item in request.attributes),
        *(item.support_basis for item in request.attributes),
        *(item.mechanism_class for item in request.mechanisms),
        *(item.rationale for item in request.mechanisms),
    ]
    haystack = " ".join(values).casefold()
    return any(term in haystack for term in _PROHIBITED_TERMS)


def _evaluations(request: StratifyContextAndSubtypeRequest) -> tuple[ContextEvaluation, ...]:
    return tuple(
        ContextEvaluation(
            attribute_id=attribute.attribute_id,
            status=(
                ContextEvaluationStatus.SUPPORTED
                if attribute.status is ContextValueStatus.OBSERVED
                else ContextEvaluationStatus.NOT_EVALUABLE
            ),
            rationale=(
                "Caller-declared observed context is replay-supported without inference."
                if attribute.status is ContextValueStatus.OBSERVED
                else (
                    "Only observed caller declarations are supported; no missing or "
                    "inferred value is promoted."
                )
            ),
            evidence=attribute.evidence,
        )
        for attribute in request.attributes
    )


class M1502ContextStratifierEngine:
    """Replay typed caller declarations with deterministic safe abstention."""

    __slots__ = ()

    def construct(self, request: object) -> LongitudinalRecurrenceContextStratificationResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        evaluations = _evaluations(validated)
        unsafe = any(item.status is not ContextEvaluationStatus.SUPPORTED for item in evaluations)
        prohibited = _contains_prohibited_proxy(validated)
        abstain = unsafe or prohibited
        if prohibited:
            finding_code = ContextFindingCode.PROHIBITED_PROXY
            finding_message = (
                "A prohibited kinase, all-omics, therapy, or treatment proxy was supplied."
            )
            support_status = SupportStatus.UNSUPPORTED
            reason = (
                "M15-02 abstained because the declaration crosses an owned responsibility boundary."
            )
        elif unsafe:
            finding_code = ContextFindingCode.INPUT_INCOMPLETE
            finding_message = (
                "One or more context declarations are missing, inferred, or not evaluable."
            )
            support_status = SupportStatus.REVIEW_REQUIRED
            reason = "M15-02 abstained because only observed caller declarations are supported."
        else:
            finding_code = ContextFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
            finding_message = (
                "Context declarations were replayed; scientific model promotion remains "
                "owner-gated."
            )
            support_status = SupportStatus.SUPPORTED
            reason = (
                "Caller-declared context and mechanisms were replayed without biological inference."
            )
        findings = (
            ContextFinding(
                finding_id=f"finding.m1502.{request_hash.removeprefix('sha256:')[:12]}",
                code=finding_code,
                message=finding_message,
                evidence=evidence[:1],
            ),
        )
        profile = None
        if not abstain:
            profile = ContextProfile(
                profile_id=f"profile.m1502.{request_hash.removeprefix('sha256:')[:24]}",
                version=M1502_CONTRACT_VERSION,
                attributes=validated.attributes,
                mechanisms=validated.mechanisms,
                reviewed_by=validated.reviewer_id,
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "output_type": "longitudinal_recurrence_context_stratification",
            "result_id": f"result.m1502.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1502_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": ContextStratificationStatus.ABSTAINED
            if abstain
            else ContextStratificationStatus.STRATIFIED,
            "profile": profile,
            "evaluations": evaluations,
            "findings": findings,
            "abstention_reason": reason if abstain else None,
            "parent_target": M1502_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=support_status,
                reason_code=("m1502_prohibited_proxy" if prohibited else "m1502_replay_supported"),
                rationale=reason,
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS,
            "human_review_required": True,
        }
        constructed = LongitudinalRecurrenceContextStratificationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> LongitudinalRecurrenceContextStratificationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1502ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1502ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1502ReplayVerificationError
        return validated


def infer_context_and_subtype(request: object) -> LongitudinalRecurrenceContextStratificationResult:
    """Public provisional M15-02 operation."""

    return M1502ContextStratifierEngine().construct(request)


__all__ = [
    "M1502AuthorizationError",
    "M1502ContextStratifierEngine",
    "M1502ReplayVerificationError",
    "infer_context_and_subtype",
    "preflight_m1502_authorization",
]
