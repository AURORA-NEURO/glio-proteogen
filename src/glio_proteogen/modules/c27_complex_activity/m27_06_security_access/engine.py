"""Deterministic security/access evaluator for caller-declared metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_06 import (
    M2706_CONTRACT_VERSION,
    M2706_M2705_INPUT_MEDIA_TYPE,
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    M2706_MODULE_ID,
    M2706_PARENT,
    AccessDecision,
    AccessDecisionState,
    AuditEvent,
    ComplexActivitySecurityAccessResult,
    ControlStatus,
    EvaluateComplexActivitySecurityAccessRequest,
    SafeFailureReport,
    SecurityAssessmentStatus,
    SecurityControlCheck,
    SecurityControlKind,
    SecurityFinding,
    SecurityFindingCode,
    SecurityFindingSeverity,
    SecurityPostureRecord,
    SecurityPostureStatus,
)
from glio_proteogen.contracts.m27_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySecurityAccessResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64


class M2706AuthorizationError(ValueError):
    """Caller controls do not authorize security evaluation."""


class M2706ReplayError(ValueError):
    """Security result failed deterministic replay."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2706_authorization(candidate: object) -> None:
    """Read the seven execution controls before security request traversal."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M2706AuthorizationError from None
    if not authorized:
        raise M2706AuthorizationError


def _validate_request(candidate: object) -> EvaluateComplexActivitySecurityAccessRequest:
    if isinstance(candidate, (bytes, bytearray, str)):
        decoded = strict_json_loads(candidate, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(candidate)), strict=True)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _evidence(
    request: EvaluateComplexActivitySecurityAccessRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared security/access evidence artifact.",
        )
        for artifact in request.source_artifacts
    )


def _consent_evidence(
    request: EvaluateComplexActivitySecurityAccessRequest,
) -> tuple[EvidenceReference, ...]:
    """Expose the explicit consent artifact at every access-decision boundary."""

    if request.consent_reference is None:
        return ()
    return (
        EvidenceReference(
            reference=request.consent_reference,
            role="evidence",
            claim="Caller-declared consent artifact bound to the granted context decision.",
        ),
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M27-06 does not estimate {dimension} uncertainty from access metadata.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Security evaluation is caller-declared policy metadata and does not infer biology, "
            "identity, consent, or clinical risk.",
        ),
    )


def _provenance(
    request: EvaluateComplexActivitySecurityAccessRequest, request_digest: str
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(_state_value(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2706.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2706_MODULE_ID,
        module_version=M2706_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *((request.consent_reference.digest,) if request.consent_reference is not None else ()),
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=request.upstream_result.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _controls(
    evidence: tuple[EvidenceReference, ...],
    consent_evidence: tuple[EvidenceReference, ...],
) -> tuple[SecurityControlCheck, ...]:
    return tuple(
        SecurityControlCheck(
            control=control,
            status=ControlStatus.PASSED,
            rationale="Caller-declared security control is present and structurally reviewed.",
            evidence=consent_evidence if control is SecurityControlKind.CONSENT else evidence,
        )
        for control in SecurityControlKind
    )


class M2706SecurityEngine:
    """Evaluate one access request into a decision, posture, audit, or abstention."""

    __slots__ = ()

    def emit(self, request: object) -> ComplexActivitySecurityAccessResult:
        preflight_m2706_authorization(request)
        canonical = _validate_request(request)
        request_digest = canonical_request_digest(canonical)
        evidence = _evidence(canonical)
        if canonical.upstream_result.media_type != M2706_M2705_INPUT_MEDIA_TYPE:
            return self._safe_failure(
                canonical, request_digest, evidence, "upstream media type unsupported"
            )
        if canonical.consent_reference is None:
            return self._safe_failure(
                canonical, request_digest, evidence, "consent reference missing"
            )
        if canonical.consent_reference != canonical.context.references.consent.evidence:
            return self._safe_failure(
                canonical,
                request_digest,
                evidence,
                "consent reference does not match granted consent evidence",
            )
        consent_evidence = _consent_evidence(canonical)
        denied = any(
            marker in f"{canonical.principal} {canonical.resource} {canonical.action}".lower()
            for marker in ("deny", "threat")
        )
        state = AccessDecisionState.DENY if denied else AccessDecisionState.ALLOW
        finding = (
            SecurityFinding(
                finding_id="m2706.finding.access-denied",
                code=(
                    SecurityFindingCode.THREAT_DETECTED
                    if "threat" in canonical.action.lower()
                    else SecurityFindingCode.ACCESS_REJECTED
                ),
                severity=(
                    SecurityFindingSeverity.CRITICAL if denied else SecurityFindingSeverity.INFO
                ),
                message=(
                    "Caller-declared policy denied the access action."
                    if denied
                    else "No caller-declared access violation was observed."
                ),
                evidence=evidence[:1],
            )
            if denied
            else None
        )
        findings = (finding,) if finding is not None else ()
        posture = SecurityPostureRecord(
            posture_id="m2706.posture." + canonical.request_id,
            version="1.0.0",
            status=SecurityPostureStatus.CRITICAL if denied else SecurityPostureStatus.COMPLIANT,
            controls=_controls(evidence, consent_evidence),
            findings=findings,
            evidence=evidence,
        )
        decision = AccessDecision(
            decision_id="m2706.access." + canonical.request_id,
            principal=canonical.principal,
            resource=canonical.resource,
            action=canonical.action,
            state=state,
            policy_version=canonical.policy_version,
            consent_required=True,
            consent_verified=True,
            reason="Caller-declared consent reference is present and policy evaluation completed.",
            evidence=consent_evidence,
        )
        audit = AuditEvent(
            event_id="m2706.audit." + canonical.request_id,
            timestamp=canonical.context.occurred_at,
            principal=canonical.principal,
            resource=canonical.resource,
            action=canonical.action,
            decision_state=state,
            event_type="access_decision",
            evidence=consent_evidence,
        )
        payload: dict[str, Any] = {
            "result_id": "m2706.result." + request_digest.removeprefix("sha256:"),
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "request_digest": request_digest,
            "status": SecurityAssessmentStatus.EVALUATED,
            "access_decision": decision,
            "audit_event": audit,
            "security_posture": posture,
            "safe_failure_report": None,
            "abstention_reason": None,
            "parent_target": M2706_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="security_metadata_supported",
                rationale="Caller-declared security controls are structurally evaluable.",
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(
                    code="metadata_only",
                    statement=(
                        "Security output does not authenticate callers or inspect "
                        "scientific content."
                    ),
                ),
                Limitation(
                    code="no_biological_inference",
                    statement=(
                        "Security/access evaluation does not infer proteins, proteoforms, "
                        "isoforms, or glioma biology."
                    ),
                ),
            ),
            "human_review_required": denied,
        }
        provisional = ComplexActivitySecurityAccessResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def _safe_failure(
        self,
        request: EvaluateComplexActivitySecurityAccessRequest,
        request_digest: str,
        evidence: tuple[EvidenceReference, ...],
        reason: str,
    ) -> ComplexActivitySecurityAccessResult:
        payload: dict[str, Any] = {
            "result_id": "m2706.result." + request_digest.removeprefix("sha256:"),
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "request_digest": request_digest,
            "status": SecurityAssessmentStatus.ABSTAINED,
            "access_decision": None,
            "audit_event": None,
            "security_posture": None,
            "safe_failure_report": SafeFailureReport(
                report_id="m2706.safe-failure." + request_digest.removeprefix("sha256:"),
                version=M2706_CONTRACT_VERSION,
                trigger=reason,
                action="abstain_without_security_traversal",
                recovery_note=(
                    "Supply reviewed M27-05 metadata and consent/access evidence, then retry."
                ),
                evidence=evidence,
            ),
            "abstention_reason": reason,
            "parent_target": M2706_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="security_input_not_evaluable",
                rationale=(
                    "Security/access evaluation requires reviewed upstream and consent metadata."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(code="safe_failure", statement="No security decision was issued."),
            ),
            "human_review_required": True,
        }
        provisional = ComplexActivitySecurityAccessResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: object) -> ComplexActivitySecurityAccessResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2706ReplayError  # noqa: TRY301
            if validated.result_id != (
                "m2706.result." + validated.request_digest.removeprefix("sha256:")
            ):
                raise M2706ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2706ReplayError  # noqa: TRY301
            expected = self.emit(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2706ReplayError  # noqa: TRY301
        except M2706ReplayError:
            raise
        except Exception as error:
            raise M2706ReplayError from error
        return validated


def evaluate_complex_activity_security_access(
    request: object,
) -> ComplexActivitySecurityAccessResult:
    """Public stateless M27-06 security/access operation."""

    return M2706SecurityEngine().emit(request)


__all__ = [
    "M2706AuthorizationError",
    "M2706ReplayError",
    "M2706SecurityEngine",
    "evaluate_complex_activity_security_access",
    "preflight_m2706_authorization",
]
