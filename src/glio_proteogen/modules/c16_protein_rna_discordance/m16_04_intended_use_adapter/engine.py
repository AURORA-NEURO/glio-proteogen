"""Deterministic, policy-first M16-04 intended-use adapter."""

# The policy boundary is intentionally explicit for audit readability.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_04 import (
    M1604_CONTRACT_VERSION,
    M1604_MODULE_ID,
    AdapterStatus,
    AdaptProteinRnaDiscordanceIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantic,
    EvidenceTier,
    IntendedUseFinding,
    IntendedUseFindingCode,
    IntendedUseObject,
    PolicyDecision,
    PolicyDecisionStatus,
    ProteinRnaDiscordanceIntendedUseResult,
    canonical_request_digest,
    result_payload_digest,
)
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

_REQUEST_ADAPTER: Final = TypeAdapter(AdaptProteinRnaDiscordanceIntendedUseRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceIntendedUseResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_FORBIDDEN_CLAIM_TERMS: Final = (
    "kinase",
    "treatment",
    "therapy",
    "all-omics",
    "identity inference",
    "consent inference",
)


class M1604AuthorizationError(PermissionError):
    """Caller controls do not authorize intended-use adaptation."""

    def __init__(self) -> None:
        super().__init__(
            "M16-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1604ReplayVerificationError(ValueError):
    """An adapter result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M16-04 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1604_authorization(candidate: object) -> None:
    """Check all seven controls before inspecting policy claim text."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001
        raise M1604AuthorizationError from None
    if states != expected:
        raise M1604AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1604_authorization(candidate)
    return candidate


def _evidence(
    request: AdaptProteinRnaDiscordanceIntendedUseRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_resolution_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        *[item.reference for item in request.policy.configuration.evidence],
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared intended-use, consent, support and provenance material.",
        )
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, supported: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "The registered policy, intended use, claim ceiling and display semantics are explicit."
            if supported
            else "The intended use or claim policy is unresolved or outside the safe domain."
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
            "The upstream artifact and policy issuer are caller-declared and not authenticated.",
            "Unsupported or missing evidence is never converted into a negative finding.",
        ),
    )


def _provenance(
    request: AdaptProteinRnaDiscordanceIntendedUseRequest, request_digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in controls
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1604_MODULE_ID,
        module_version=M1604_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_resolution_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _claim_text(policy: object) -> tuple[str, ...]:
    permitted = getattr(policy, "permitted_claims", ())
    return tuple(str(value).casefold() for value in permitted)


def _policy_evaluation(
    request: AdaptProteinRnaDiscordanceIntendedUseRequest,
) -> tuple[bool, PolicyDecisionStatus, tuple[tuple[IntendedUseFindingCode, str], ...]]:
    policy = request.policy
    findings: list[tuple[IntendedUseFindingCode, str]] = []
    text = _claim_text(policy)
    if any(term in claim for claim in text for term in _FORBIDDEN_CLAIM_TERMS):
        findings.append(
            (
                IntendedUseFindingCode.CLAIM_CEILING_EXCEEDED,
                "Policy text requests a prohibited kinase, treatment, fusion, or identity/consent interpretation.",
            )
        )
    if policy.maximum_claim_ceiling is ClaimCeiling.ABSTAIN:
        findings.append(
            (
                IntendedUseFindingCode.DISPLAY_RESTRICTED,
                "The registered policy explicitly sets an abstaining claim ceiling.",
            )
        )
    if policy.display_semantic is DisplaySemantic.HIDDEN:
        findings.append(
            (
                IntendedUseFindingCode.DISPLAY_RESTRICTED,
                "The registered policy hides the object from ordinary display.",
            )
        )
    if policy.minimum_evidence_tier is EvidenceTier.EXPLORATORY:
        return not findings, PolicyDecisionStatus.QUALIFIED, tuple(findings)
    if findings:
        return False, PolicyDecisionStatus.BLOCKED, tuple(findings)
    return True, PolicyDecisionStatus.ALLOWED, tuple(findings)


def _policy_decision(
    request: AdaptProteinRnaDiscordanceIntendedUseRequest,
    status: PolicyDecisionStatus,
    reasons: tuple[str, ...],
    evidence: tuple[EvidenceReference, ...],
) -> PolicyDecision:
    return PolicyDecision(
        decision_id=f"decision.{canonical_request_digest(request).removeprefix('sha256:')}",
        status=status,
        policy_id=request.policy.policy_id,
        reasons=reasons,
        evidence=evidence if status is PolicyDecisionStatus.ALLOWED else evidence[:1],
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_policy",
            statement="Policy registration, evidence tier, claim ceiling, and display semantics are caller-declared.",
        ),
        Limitation(
            code="prohibited_outputs",
            statement="No kinase activity, all-omics fusion, treatment recommendation, or identity inference is emitted.",
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No intended-use object is published outside the registered policy domain.",
            )
        )
    return tuple(values)


class M1604IntendedUseAdapterEngine:
    """Convert an opaque upstream result into a bounded registered policy object."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinRnaDiscordanceIntendedUseResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: AdaptProteinRnaDiscordanceIntendedUseRequest
    ) -> ProteinRnaDiscordanceIntendedUseResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, decision_status, policy_findings = _policy_evaluation(request)
        reasons = tuple(message for _, message in policy_findings)
        if not reasons:
            reasons = (
                "Registered intended use satisfies the locked evidence, claim, and display policy.",
            )
        decision = _policy_decision(request, decision_status, reasons, evidence)
        findings = tuple(
            IntendedUseFinding(
                finding_id=f"finding.{index}.{request_hash.removeprefix('sha256:')[:12]}",
                code=code,
                message=message,
                evidence=evidence[:1],
            )
            for index, (code, message) in enumerate(policy_findings, start=1)
        )
        object_value = (
            IntendedUseObject(
                object_id=f"intended-use.{request_hash.removeprefix('sha256:')}",
                version=M1604_CONTRACT_VERSION,
                upstream_artifact=request.upstream_resolution_result,
                context=request.policy.context,
                audience=request.policy.audience,
                evidence_tier=request.policy.minimum_evidence_tier,
                claim_ceiling=request.policy.maximum_claim_ceiling,
                display_semantic=request.policy.display_semantic,
                permitted_claims=request.policy.permitted_claims,
                blocked_claims=request.policy.prohibited_claims,
                policy_decision=decision,
                material_assumptions=(
                    "Upstream result is referenced by digest and is not dereferenced or relabeled.",
                    "Policy issuer and evidence tier remain caller-declared pending review.",
                ),
                evidence=evidence,
            )
            if supported
            else None
        )
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_intended_use",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1604_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": AdapterStatus.ADAPTED if supported else AdapterStatus.ABSTAINED,
            "intended_use_object": object_value,
            "policy_decision": decision,
            "findings": findings,
            "abstention_reason": None
            if supported
            else "The intended-use policy is outside the adapter's safe claim and display domain.",
            "parent_target": "protein_rna_discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1604_policy_supported" if supported else "m1604_policy_abstained",
                rationale="Registered policy is compatible with the adapter safety boundary."
                if supported
                else "Policy requires review before an intended-use object can be published.",
            ),
            "uncertainty": _uncertainty(supported=supported),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinRnaDiscordanceIntendedUseResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceIntendedUseResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1604ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1604ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1604ReplayVerificationError
        return validated


def adapt_protein_rna_discordance_intended_use(
    request: object,
) -> ProteinRnaDiscordanceIntendedUseResult:
    """Public provisional M16-04 operation."""

    return M1604IntendedUseAdapterEngine().infer(request)


__all__ = [
    "M1604AuthorizationError",
    "M1604IntendedUseAdapterEngine",
    "M1604ReplayVerificationError",
    "adapt_protein_rna_discordance_intended_use",
    "preflight_m1604_authorization",
]
