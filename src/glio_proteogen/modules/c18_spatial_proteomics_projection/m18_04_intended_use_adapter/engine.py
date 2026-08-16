"""Replay-safe intended-use policy adaptation for M18-04."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_04 import (
    M1804_CONTRACT_VERSION,
    M1804_EVIDENCE_CLAIM,
    M1804_MODULE_ID,
    AdaptBiomarkerPanelIntendedUseRequest,
    AdapterFinding,
    AdapterFindingCode,
    AdapterStatus,
    BiomarkerPanelIntendedUseAdapterResult,
    IntendedUseKind,
    IntendedUseSpecificObject,
    PolicyDecision,
    PolicyDecisionStatus,
)
from glio_proteogen.contracts.m18_04.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdaptBiomarkerPanelIntendedUseRequest)
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
_AUDIENCES: Final = frozenset(
    {"research", "internal_validation", "clinical_review", "release_review"}
)
_MINIMUM_EVIDENCE_TIER: Final = {
    IntendedUseKind.RESEARCH: 1,
    IntendedUseKind.INTERNAL_VALIDATION: 2,
    IntendedUseKind.CLINICAL_REVIEW: 3,
    IntendedUseKind.RELEASE_REVIEW: 4,
}
_REQUIRED_DISPLAY_SECTIONS: Final = frozenset(
    {"support", "uncertainty", "provenance", "evidence", "limitations"}
)
_TREATMENT_TERMS: Final = frozenset(
    {"treatment", "therapy", "therapeutic", "recommendation", "clinical recommendation"}
)
_FORBIDDEN_CLAIM_TERMS: Final = frozenset(
    {"kinase", "all-omics", "identity inference", "diagnosis", "subtype"}
)


class M1804AuthorizationError(ValueError):
    """Raised before intended-use or claim traversal when controls are unsafe."""


class M1804ReplayError(ValueError):
    """Raised when a result digest no longer binds to its request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1804_authorization(candidate: object) -> None:
    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1804AuthorizationError("M18-04 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1804AuthorizationError(  # noqa: TRY003
                f"M18-04 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M18-04 adapts declared use policy; it does not estimate biology.",
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
            "Display and claim eligibility are sensitive to audience, evidence tier, "
            "claim ceiling, and disclosure sections.",
        ),
    )


def _control_decisions(
    request: AdaptBiomarkerPanelIntendedUseRequest,
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


def _provenance(request: AdaptBiomarkerPanelIntendedUseRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1804_MODULE_ID,
        module_version=M1804_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(item.reference.digest for item in request.registration.evidence),
        ),
        configuration_digest=sha256_digest(request.registration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: AdaptBiomarkerPanelIntendedUseRequest) -> tuple[EvidenceReference, ...]:
    return (
        tuple(
            EvidenceReference(reference=item, role="evidence", claim=M1804_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        + request.registration.evidence
        + request.registration.claim_ceiling.evidence
        + request.registration.display_semantics.evidence
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="intended_use_policy_only",
            statement="This adapter applies caller-declared use policy and does not infer biology.",
        ),
        Limitation(
            code="upstream_not_authenticated",
            statement="The upstream M18-03 artifact and issuer authority are not authenticated.",
        ),
        Limitation(
            code="no_treatment_or_kinase_claim",
            statement="Treatment, kinase, identity and subtype claims remain outside this adapter.",
        ),
    )


def _policy_decision(
    request: AdaptBiomarkerPanelIntendedUseRequest,
) -> tuple[PolicyDecision, tuple[AdapterFinding, ...], bool]:
    registration = request.registration
    claim_text = registration.claim_ceiling.maximum_claim.lower()
    findings: list[AdapterFinding] = []
    blocked_claims: list[str] = []
    if registration.audience not in _AUDIENCES:
        findings.append(
            AdapterFinding(
                finding_id=f"finding.{request.request_id}.audience",
                code=AdapterFindingCode.AUDIENCE_UNSUPPORTED,
                message="Registered audience is outside the supported audience vocabulary.",
            )
        )
        blocked_claims.append("audience")
    if registration.evidence_tier < _MINIMUM_EVIDENCE_TIER[registration.intended_use]:
        findings.append(
            AdapterFinding(
                finding_id=f"finding.{request.request_id}.evidence-tier",
                code=AdapterFindingCode.EVIDENCE_TIER_MISSING,
                message="Evidence tier is below the minimum for the registered intended use.",
            )
        )
        blocked_claims.append("evidence tier")
    if not _REQUIRED_DISPLAY_SECTIONS.issubset(set(registration.display_semantics.section_order)):
        findings.append(
            AdapterFinding(
                finding_id=f"finding.{request.request_id}.display",
                code=AdapterFindingCode.DISPLAY_SEMANTICS_INCOMPLETE,
                message=(
                    "Display semantics must disclose support, uncertainty, provenance, "
                    "evidence and limitations."
                ),
            )
        )
        blocked_claims.append("display semantics")
    treatment_terms = sorted(term for term in _TREATMENT_TERMS if term in claim_text)
    if treatment_terms:
        findings.append(
            AdapterFinding(
                finding_id=f"finding.{request.request_id}.treatment",
                code=AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED,
                message="Treatment or therapeutic recommendation claims are blocked.",
            )
        )
        blocked_claims.extend(treatment_terms)
    forbidden_terms = sorted(term for term in _FORBIDDEN_CLAIM_TERMS if term in claim_text)
    if forbidden_terms:
        findings.append(
            AdapterFinding(
                finding_id=f"finding.{request.request_id}.ceiling",
                code=AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
                message="Claim ceiling contains an interpretation outside M18-04 authority.",
            )
        )
        blocked_claims.extend(forbidden_terms)
    if findings:
        return (
            PolicyDecision(
                status=PolicyDecisionStatus.BLOCKED,
                reason_code=findings[0].code,
                rationale="Intended-use policy blocked one or more claims or disclosures.",
                blocked_claims=tuple(dict.fromkeys(blocked_claims)),
                evidence=_evidence(request),
            ),
            tuple(findings),
            True,
        )
    status = (
        PolicyDecisionStatus.REVIEW_REQUIRED
        if registration.intended_use
        in {IntendedUseKind.CLINICAL_REVIEW, IntendedUseKind.RELEASE_REVIEW}
        else PolicyDecisionStatus.ALLOWED
    )
    return (
        PolicyDecision(
            status=status,
            reason_code=AdapterFindingCode.ALLOWED,
            rationale="Registered intended use and disclosure policy are satisfied.",
            evidence=_evidence(request),
        ),
        (),
        False,
    )


class M1804Engine:
    """Adapt a declared upstream result into a bounded intended-use object."""

    def validate_request(self, candidate: object) -> AdaptBiomarkerPanelIntendedUseRequest:
        preflight_m1804_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adapt(self, candidate: object) -> BiomarkerPanelIntendedUseAdapterResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        policy, findings, blocked = _policy_decision(request)
        if blocked:
            status = AdapterStatus.ABSTAINED
            adapted_object = None
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="intended_use_policy_blocked",
                rationale="No object is emitted while a policy claim is blocked.",
            )
            abstention_reason = "Intended-use policy blocked the requested object."
        else:
            status = AdapterStatus.ADAPTED
            adapted_object = IntendedUseSpecificObject(
                object_id=f"object.{request.request_id}",
                version=M1804_CONTRACT_VERSION,
                upstream_result=request.upstream_result,
                registration=request.registration,
                policy_decision=policy,
                uncertainty=_uncertainty(),
                evidence=_evidence(request),
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="intended_use_registered",
                rationale="A registered intended-use policy permits the bounded object.",
            )
            abstention_reason = None
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_intended_use_adapter_result",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1804_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "adapted_object": adapted_object,
            "policy_decision": policy,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": bool(findings)
            or policy.status is PolicyDecisionStatus.REVIEW_REQUIRED,
        }
        payload["result_digest"] = result_payload_digest(
            BiomarkerPanelIntendedUseAdapterResult.model_construct(**payload)
        )
        return BiomarkerPanelIntendedUseAdapterResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: BiomarkerPanelIntendedUseAdapterResult,
    ) -> BiomarkerPanelIntendedUseAdapterResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1804ReplayError("M18-04 result request digest mismatch")  # noqa: TRY003
        if result.result_id != f"result.{result.request_digest.removeprefix('sha256:')}":
            raise M1804ReplayError("M18-04 result identifier mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1804ReplayError("M18-04 result payload digest mismatch")  # noqa: TRY003
        return result


def adapt_biomarker_panel_intended_use(
    candidate: object,
) -> BiomarkerPanelIntendedUseAdapterResult:
    return M1804Engine().adapt(candidate)


__all__ = [
    "M1804AuthorizationError",
    "M1804Engine",
    "M1804ReplayError",
    "adapt_biomarker_panel_intended_use",
    "preflight_m1804_authorization",
]
