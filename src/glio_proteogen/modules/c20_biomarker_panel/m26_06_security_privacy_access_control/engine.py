"""Deterministic M26-06 security posture and access-decision runtime.

The runtime is intentionally caller-declared.  It never traverses protected
payloads, resolves identity, infers consent, or treats an unavailable control as
negative evidence.  Seven upstream control references are checked before any
request material is evaluated, and every security control is preserved in the
posture and provenance envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_06 import (
    M2606_CONTRACT_VERSION,
    M2606_MODULE_ID,
    AccessDecision,
    AccessDecisionState,
    AuditEvent,
    ControlStatus,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
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
from glio_proteogen.contracts.m26_06.canonical import (
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
    ExecutionContext,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EvaluateProteomicsSecurityAccessRequest]] = TypeAdapter(
    EvaluateProteomicsSecurityAccessRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteomicsSecurityAccessResult]] = TypeAdapter(
    ProteomicsSecurityAccessResult
)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROL_STATES: Final[dict[ControlRole, str]] = {
    ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
    ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.CONSENT: ConsentState.GRANTED.value,
    ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
}
_LIMITATIONS: Final = (
    Limitation(
        code="caller_declared_security",
        statement=(
            "Security controls are evaluated from immutable caller-declared evidence; this "
            "module does not certify infrastructure or inspect protected payloads."
        ),
    ),
    Limitation(
        code="no_identity_or_consent_inference",
        statement=(
            "Identity, consent, treatment, kinase activity, and all-omics conclusions are "
            "never inferred by M26-06."
        ),
    ),
    Limitation(
        code="provisional_owner_review",
        statement=(
            "The ABI is provisional pending owner confirmation and independent security "
            "review of policy, retention, transport, and deployment controls."
        ),
    ),
)


class M2606AuthorizationError(ValueError):
    """Upstream authorization controls do not permit security evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M26-06 requires accepted configuration, resolved identity, granted consent, "
            "and accepted provenance, quality, support, and intended-use controls"
        )


class M2606ReplayError(ValueError):
    """A security result failed canonical replay verification."""

    def __init__(self) -> None:
        super().__init__("M26-06 security result replay verification failed")


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2606_authorization(candidate: object) -> None:
    """Fail closed on every upstream control before evaluating declarations."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        authorized = all(
            _state(_member(references, role.value)) == expected
            for role, expected in _EXPECTED_CONTROL_STATES.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings must fail closed.
        raise M2606AuthorizationError from None
    if not authorized:
        raise M2606AuthorizationError


def _evidence(request: EvaluateProteomicsSecurityAccessRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M26-06 security evidence; issuer authority and protected "
                "payload contents are not authenticated or traversed."
            ),
        )
        for artifact in request.source_artifacts
    )


def _declaration_evidence(
    request: EvaluateProteomicsSecurityAccessRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        item for declaration in request.control_declarations for item in declaration.evidence
    )


def _findings(
    request: EvaluateProteomicsSecurityAccessRequest,
) -> tuple[SecurityFinding, ...]:
    evidence = (*_evidence(request), *_declaration_evidence(request))
    findings: list[SecurityFinding] = []
    for declaration in request.control_declarations:
        if declaration.status is ControlStatus.FAILED:
            if declaration.control is SecurityControlKind.CONSENT:
                code = SecurityFindingCode.CONSENT_MISSING
                severity = SecurityFindingSeverity.CRITICAL
            elif declaration.control is SecurityControlKind.THREAT_DETECTION:
                code = SecurityFindingCode.THREAT_DETECTED
                severity = SecurityFindingSeverity.CRITICAL
            elif declaration.control is SecurityControlKind.LEAST_PRIVILEGE:
                code = SecurityFindingCode.ACCESS_REJECTED
                severity = SecurityFindingSeverity.ERROR
            else:
                code = SecurityFindingCode.CONTROL_FAILED
                severity = SecurityFindingSeverity.CRITICAL
            findings.append(
                SecurityFinding(
                    finding_id=f"finding.m2606.{declaration.control.value}.failed",
                    code=code,
                    severity=severity,
                    message=(
                        f"security control {declaration.control.value} was declared failed; "
                        "access is not evaluated"
                    ),
                    evidence=evidence,
                )
            )
        elif declaration.status in {ControlStatus.NOT_EVALUABLE, ControlStatus.REVIEW_REQUIRED}:
            findings.append(
                SecurityFinding(
                    finding_id=f"finding.m2606.{declaration.control.value}.unresolved",
                    code=SecurityFindingCode.UNSUPPORTED_POLICY,
                    severity=SecurityFindingSeverity.WARNING,
                    message=(
                        f"security control {declaration.control.value} is unresolved; "
                        "no access conclusion is emitted"
                    ),
                    evidence=evidence,
                )
            )
    if not findings:
        findings.append(
            SecurityFinding(
                finding_id="finding.m2606.provisional-review",
                code=SecurityFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                severity=SecurityFindingSeverity.INFO,
                message="Provisional M26-06 ABI remains subject to owner security review.",
                evidence=evidence,
            )
        )
    return tuple(findings)


def _controls(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
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
            state=getattr(reference.state, "value", reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(
    request: EvaluateProteomicsSecurityAccessRequest,
    request_digest: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = request.context.references
    configuration_digest = sha256_digest(
        {
            "module": M2606_MODULE_ID,
            "contract": M2606_CONTRACT_VERSION,
            "operation": request.operation,
            "upstream": request.upstream_result.media_type,
            "policy_version": request.policy_version,
            "requested_controls": tuple(item.value for item in request.requested_controls),
        }
    )
    return ProvenanceRecord(
        activity_id=f"activity.m2606.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2606_MODULE_ID,
        module_version=M2606_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_digest,
                    request.upstream_result.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M26-06 does not estimate {dimension} uncertainty.",
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
            "A caller-declared security control is not an independent certification.",
            "Unresolved controls abstain and never become negative evidence.",
        ),
    )


def _posture(
    request: EvaluateProteomicsSecurityAccessRequest,
    findings: tuple[SecurityFinding, ...],
) -> SecurityPostureRecord:
    evidence = (*_evidence(request), *_declaration_evidence(request))
    statuses = {item.status for item in request.control_declarations}
    if statuses == {ControlStatus.PASSED}:
        status = SecurityPostureStatus.COMPLIANT
    elif ControlStatus.FAILED in statuses:
        status = SecurityPostureStatus.CRITICAL
    else:
        # The contract fixes the eight-control vocabulary.  Once the all-pass
        # and failed cases are excluded, only an unresolved/review state remains.
        status = SecurityPostureStatus.NOT_EVALUABLE
    checks = tuple(
        SecurityControlCheck(
            control=item.control,
            status=item.status,
            rationale=item.rationale,
            evidence=item.evidence,
        )
        for item in request.control_declarations
    )
    return SecurityPostureRecord(
        posture_id=f"posture.m2606.{canonical_request_digest(request).removeprefix('sha256:')}",
        version=M2606_CONTRACT_VERSION,
        status=status,
        controls=checks,
        findings=findings,
        evidence=evidence,
    )


def _safe_failure(
    request: EvaluateProteomicsSecurityAccessRequest,
    findings: tuple[SecurityFinding, ...],
) -> SafeFailureReport:
    return SafeFailureReport(
        report_id="safe-failure.m2606.security-access",
        version=M2606_CONTRACT_VERSION,
        trigger=", ".join(sorted({item.code.value for item in findings})),
        action=(
            "Do not grant or deny access from this assessment; route the unresolved security "
            "control set to an authorized reviewer."
        ),
        recovery_note=(
            "Supply fresh evidence for every failed or unresolved control and rerun under the "
            "same policy version."
        ),
        evidence=(*_evidence(request), *_declaration_evidence(request)),
    )


def _build_result(
    request: EvaluateProteomicsSecurityAccessRequest,
) -> ProteomicsSecurityAccessResult:
    request_digest = canonical_request_digest(request)
    findings = _findings(request)
    all_passed = all(item.status is ControlStatus.PASSED for item in request.control_declarations)
    controls = _controls(request.context)
    provenance = _provenance(request, request_digest, controls)
    evidence = (*_evidence(request), *_declaration_evidence(request))
    posture = _posture(request, findings)
    evaluated = all_passed and request.context.references.consent.state is ConsentState.GRANTED
    status = SecurityAssessmentStatus.EVALUATED if evaluated else SecurityAssessmentStatus.ABSTAINED
    decision_state = (
        AccessDecisionState.ALLOW
        if evaluated
        else (
            AccessDecisionState.DENY
            if any(item.status is ControlStatus.FAILED for item in request.control_declarations)
            else AccessDecisionState.REVIEW_REQUIRED
        )
    )
    decision = (
        AccessDecision(
            decision_id=f"decision.m2606.{request_digest.removeprefix('sha256:')}",
            principal=request.principal,
            resource=request.resource,
            action=request.action,
            state=decision_state,
            policy_version=request.policy_version,
            consent_required=True,
            consent_verified=request.context.references.consent.state is ConsentState.GRANTED,
            reason=(
                "Every requested control passed under the supplied policy and consent."
                if evaluated
                else "Security assessment did not establish a supported access decision."
            ),
            evidence=evidence,
        )
        if evaluated
        else None
    )
    audit = (
        AuditEvent(
            event_id=f"audit.m2606.{request_digest.removeprefix('sha256:')}",
            timestamp=request.context.occurred_at,
            principal=request.principal,
            resource=request.resource,
            action=request.action,
            decision_state=decision_state,
            event_type="security_access_evaluation",
            evidence=evidence,
        )
        if evaluated
        else None
    )
    candidate: dict[str, Any] = {
        "output_type": "proteomics_security_access",
        "result_id": f"result.m2606.{request_digest.removeprefix('sha256:')}",
        "result_version": M2606_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "access_decision": decision,
        "audit_event": audit,
        "security_posture": posture,
        "safe_failure_report": None if evaluated else _safe_failure(request, findings),
        "abstention_reason": None
        if evaluated
        else "Security controls are failed or unresolved; no access conclusion is emitted.",
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED if evaluated else SupportStatus.REVIEW_REQUIRED,
            reason_code="security_access_supported" if evaluated else "security_access_abstained",
            rationale=(
                "All caller-declared security controls passed with granted upstream consent."
                if evaluated
                else "Security controls are not jointly evaluable; abstention is explicit."
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": _LIMITATIONS,
        "human_review_required": not evaluated,
    }
    materialized = ProteomicsSecurityAccessResult.model_construct(**candidate)
    payload = materialized.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M2606SecurityEngine:
    """Build deterministic security results without I/O or protected data access."""

    __slots__ = ()

    def evaluate(
        self, request: EvaluateProteomicsSecurityAccessRequest
    ) -> ProteomicsSecurityAccessResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2606_authorization(validated)
        return _build_result(validated)


def evaluate_proteomics_security_access(request: object) -> ProteomicsSecurityAccessResult:
    """Public stateless M26-06 entry point."""

    return M2606SecurityEngine().evaluate(_REQUEST_ADAPTER.validate_python(request, strict=True))


def verify_security_access_result(
    result: ProteomicsSecurityAccessResult,
) -> ProteomicsSecurityAccessResult:
    """Revalidate canonical request/result digests and safe-status closure."""

    try:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
    except ValidationError as error:
        raise M2606ReplayError from error
    return validated


__all__ = [
    "M2606AuthorizationError",
    "M2606ReplayError",
    "M2606SecurityEngine",
    "evaluate_proteomics_security_access",
    "preflight_m2606_authorization",
    "verify_security_access_result",
]
