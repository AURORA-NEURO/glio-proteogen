"""Deterministic, replay-safe intended-use adaptation for M20-04."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_04 import (
    M2004_CONTRACT_VERSION,
    M2004_EVIDENCE_CLAIM,
    M2004_MAX_EVIDENCE,
    M2004_MODULE_ID,
    AdapterFinding,
    AdapterFindingCode,
    AdapterStatus,
    AdaptProteinSubtypeIntendedUseRequest,
    IntendedUseSpecificObject,
    PolicyDecision,
    PolicyDecisionStatus,
    ProteinSubtypeIntendedUseAdapterResult,
)
from glio_proteogen.contracts.m20_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AdaptProteinSubtypeIntendedUseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeIntendedUseAdapterResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}
_FORBIDDEN_TERMS: Final = frozenset(
    {"treatment", "diagnos", "kinase", "all-omics", "identity inference"}
)
_REQUIRED_DISPLAY_SECTIONS: Final = frozenset({"support", "uncertainty", "evidence", "limitations"})
_MIN_REVIEW_EVIDENCE_TIER: Final = 3


class M2004AuthorizationError(ValueError):
    """Raised before adaptation when a required control is unsafe."""


class M2004ReplayError(ValueError):
    """Raised when a result no longer binds to its exact request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m2004_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before reading source metadata."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M2004AuthorizationError("M20-04 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M2004AuthorizationError(  # noqa: TRY003
                f"M20-04 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M20-04 adapts caller-declared presentation policy; it does not estimate "
            "biological truth."
        ),
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
            "Interpretation is sensitive to the locked registration, evidence tier, audience, "
            "display semantics, upstream support and the provisional ABI.",
        ),
    )


def _control_decisions(
    request: AdaptProteinSubtypeIntendedUseRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    records.extend(
        (
            ControlDecisionRecord(
                role=ControlRole.IDENTITY_LINEAGE,
                decision_id=refs.identity_lineage.decision_id,
                state=refs.identity_lineage.state.value,
                policy_version=refs.identity_lineage.policy_version,
                evidence_digest=refs.identity_lineage.evidence.digest,
                subject_digest=refs.identity_lineage.binding_digest,
            ),
            ControlDecisionRecord(
                role=ControlRole.CONSENT,
                decision_id=refs.consent.decision_id,
                state=refs.consent.state.value,
                policy_version=refs.consent.policy_version,
                evidence_digest=refs.consent.evidence.digest,
            ),
        )
    )
    return tuple(records)


def _provenance(request: AdaptProteinSubtypeIntendedUseRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        dict.fromkeys(
            (
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                *(item.reference.digest for item in request.registration.evidence),
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M2004_MODULE_ID,
        module_version=M2004_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.registration.model_dump(mode="json")),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AdaptProteinSubtypeIntendedUseRequest) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = []
    seen: set[str] = set()
    candidates = (
        EvidenceReference(
            reference=request.upstream_result,
            role="evidence",
            claim="Caller-declared M20-03 integrated protein subtype result.",
        ),
        *(
            EvidenceReference(reference=artifact, role="evidence", claim=M2004_EVIDENCE_CLAIM)
            for artifact in request.source_artifacts
        ),
        *request.registration.evidence,
        *request.registration.claim_ceiling.evidence,
        *request.registration.display_semantics.evidence,
    )
    for evidence in candidates:
        if evidence.reference.digest not in seen and len(items) < M2004_MAX_EVIDENCE:
            seen.add(evidence.reference.digest)
            items.append(evidence)
    return tuple(items)


def _finding(
    request: AdaptProteinSubtypeIntendedUseRequest,
    code: AdapterFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> AdapterFinding:
    return AdapterFinding(
        finding_id=f"finding.{request.request_id}.{code.value}",
        code=code,
        message=message,
        evidence=evidence,
    )


def _findings(request: AdaptProteinSubtypeIntendedUseRequest) -> tuple[AdapterFinding, ...]:
    registration = request.registration
    evidence = _evidence(request)
    findings: list[AdapterFinding] = []
    claim = registration.claim_ceiling.maximum_claim.casefold()
    prohibited = " ".join(
        item.casefold() for item in registration.claim_ceiling.prohibited_interpretations
    )
    if "treatment" in claim or "treatment" in prohibited:
        findings.append(
            _finding(
                request,
                AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED,
                "Treatment recommendations are outside the M20-04 intended-use boundary.",
                evidence,
            )
        )
    if any(term in claim for term in _FORBIDDEN_TERMS - {"treatment"}):
        findings.append(
            _finding(
                request,
                AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
                "The registered maximum claim crosses a prohibited interpretation boundary.",
                evidence,
            )
        )
    if (
        registration.intended_use.value in {"clinical_review", "release_review"}
        and registration.evidence_tier < _MIN_REVIEW_EVIDENCE_TIER
    ):
        findings.append(
            _finding(
                request,
                AdapterFindingCode.EVIDENCE_TIER_MISSING,
                "Clinical or release review requires evidence tier 3 or 4.",
                evidence,
            )
        )
    if not _REQUIRED_DISPLAY_SECTIONS.issubset(
        {section.casefold() for section in registration.display_semantics.section_order}
    ):
        findings.append(
            _finding(
                request,
                AdapterFindingCode.DISPLAY_SEMANTICS_INCOMPLETE,
                "Display semantics must expose support, uncertainty, evidence and limitations.",
                evidence,
            )
        )
    return tuple(findings)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="caller_declared_policy",
            statement=(
                "Registration, audience, evidence tier and claim ceiling are caller-declared "
                "and not issuer-authenticated."
            ),
        ),
        Limitation(
            code="upstream_not_recomputed",
            statement=(
                "M20-04 binds the M20-03 artifact by media type and does not recompute or "
                "authenticate upstream biology."
            ),
        ),
        Limitation(
            code="no_treatment_or_kinase",
            statement=(
                "Treatment, kinase, all-omics, diagnosis and identity-inference "
                "interpretations remain outside this adapter."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "The ABI remains provisional pending owner confirmation and release "
                "governance."
            ),
        ),
    )


class M2004Engine:
    """Adapt one bounded M20-03 artifact into a registered intended-use object."""

    def validate_request(self, candidate: object) -> AdaptProteinSubtypeIntendedUseRequest:
        preflight_m2004_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adapt(self, candidate: object) -> ProteinSubtypeIntendedUseAdapterResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        evidence = _evidence(request)
        findings = _findings(request)
        if findings:
            status = AdapterStatus.ABSTAINED
            adapted_object = None
            policy_status = (
                PolicyDecisionStatus.BLOCKED
                if any(
                    item.code is AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED
                    for item in findings
                )
                else PolicyDecisionStatus.REVIEW_REQUIRED
            )
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="intended_use_review_required",
                rationale=(
                    "No bounded object is emitted while registration policy findings "
                    "require review."
                ),
            )
            abstention_reason = (
                "M20-04 abstained because intended-use policy findings require review."
            )
        else:
            status = AdapterStatus.ADAPTED
            policy_status = PolicyDecisionStatus.ALLOWED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="intended_use_policy_allowed",
                rationale=(
                    "The locked registration satisfies the bounded M20-04 display and "
                    "claim policy."
                ),
            )
            abstention_reason = None
        policy = PolicyDecision(
            status=policy_status,
            reason_code=(
                findings[0].code if findings else AdapterFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
            ),
            rationale=(
                "Registered policy permits bounded protein subtype presentation."
                if not findings
                else "At least one registered claim, evidence, or display boundary requires review."
            ),
            blocked_claims=(request.registration.claim_ceiling.maximum_claim,) if findings else (),
            evidence=evidence,
        )
        if adapted_object is None and not findings:
            adapted_object = IntendedUseSpecificObject(
                object_id=f"object.{request.request_id}",
                version=request.registration.version,
                upstream_result=request.upstream_result,
                registration=request.registration,
                policy_decision=policy,
                uncertainty=_uncertainty(),
                evidence=evidence,
            )
        payload: dict[str, Any] = {
            "output_type": "protein_subtype_intended_use_adapter_result",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M2004_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "adapted_object": adapted_object,
            "policy_decision": policy,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": bool(findings),
        }
        payload["result_digest"] = result_payload_digest(
            ProteinSubtypeIntendedUseAdapterResult.model_construct(**payload)
        )
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(
        self,
        result: ProteinSubtypeIntendedUseAdapterResult,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M2004ReplayError("M20-04 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M2004ReplayError("M20-04 result payload digest mismatch")  # noqa: TRY003
        return _RESULT_ADAPTER.validate_python(result, strict=True)


def adapt_protein_subtype_intended_use(candidate: object) -> ProteinSubtypeIntendedUseAdapterResult:
    return M2004Engine().adapt(candidate)


__all__ = [
    "M2004AuthorizationError",
    "M2004Engine",
    "M2004ReplayError",
    "adapt_protein_subtype_intended_use",
    "preflight_m2004_authorization",
]
