"""Provisional M27-06 security, privacy, and access-control contracts.

The dossier calls for least privilege, encryption, secrets, isolation,
consent, de-identification, audit, and threat detection. This scaffold keeps
those controls typed and auditable while unresolved support abstains.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m27_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 9616-9656. Owner confirmation and implementation details remain
# pending.
M2706_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-06"
M2706_OPERATION: Final = "evaluate_complex_activity_security_access"
M2706_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2706_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-06+json"
M2706_M2705_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-05+json"
M2706_PARENT: Final = "complex activity"
M2706_OWNER: Final = "Platform engineering"
M2706_SAFETY_CLASS: Final = "S3"
M2706_GATE: Final = "G4"
M2706_PROVISIONAL_ABI: Final = True
M2706_MAX_EVIDENCE: Final = 64
M2706_MAX_FINDINGS: Final = 64
M2706_MAX_CONTROLS: Final = 8
M2706_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2706_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class SecurityControlKind(StrEnum):
    LEAST_PRIVILEGE = "least_privilege"
    ENCRYPTION = "encryption"
    SECRETS = "secrets"
    ISOLATION = "isolation"
    CONSENT = "consent"
    DE_IDENTIFICATION = "de_identification"
    AUDIT = "audit"
    THREAT_DETECTION = "threat_detection"


class ControlStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"
    REVIEW_REQUIRED = "review_required"


class AccessDecisionState(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"
    ABSTAIN_UNSUPPORTED = "abstain_unsupported"


class SecurityPostureStatus(StrEnum):
    COMPLIANT = "compliant"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    NOT_EVALUABLE = "not_evaluable"


class SecurityAssessmentStatus(StrEnum):
    EVALUATED = "evaluated"
    ABSTAINED = "abstained"


class SecurityFindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SecurityFindingCode(StrEnum):
    CONSENT_MISSING = "consent_missing"
    CONTROL_FAILED = "control_failed"
    THREAT_DETECTED = "threat_detected"
    ACCESS_REJECTED = "access_rejected"
    UNSUPPORTED_POLICY = "unsupported_policy"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class SecurityControlCheck(FrozenModel):
    control: SecurityControlKind
    status: ControlStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2706_MAX_EVIDENCE)


class AccessDecision(FrozenModel):
    decision_id: Identifier
    principal: NonEmptyStr
    resource: NonEmptyStr
    action: NonEmptyStr
    state: AccessDecisionState
    policy_version: SemanticVersion
    consent_required: bool
    consent_verified: bool
    reason: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2706_MAX_EVIDENCE)

    @model_validator(mode="after")
    def consent_is_enforced(self) -> AccessDecision:
        if (
            self.consent_required
            and not self.consent_verified
            and self.state is AccessDecisionState.ALLOW
        ):
            raise ValueError("access cannot be allowed without required consent")
        return self


class AuditEvent(FrozenModel):
    event_id: Identifier
    timestamp: AwareDatetime
    principal: NonEmptyStr
    resource: NonEmptyStr
    action: NonEmptyStr
    decision_state: AccessDecisionState
    event_type: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2706_MAX_EVIDENCE)


class SecurityFinding(FrozenModel):
    finding_id: Identifier
    code: SecurityFindingCode
    severity: SecurityFindingSeverity
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2706_MAX_EVIDENCE)


class SecurityPostureRecord(FrozenModel):
    posture_id: Identifier
    version: SemanticVersion
    status: SecurityPostureStatus
    controls: tuple[SecurityControlCheck, ...] = Field(
        min_length=M2706_MAX_CONTROLS, max_length=M2706_MAX_CONTROLS
    )
    findings: tuple[SecurityFinding, ...] = Field(default=(), max_length=M2706_MAX_FINDINGS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2706_MAX_EVIDENCE)

    @model_validator(mode="after")
    def controls_are_unique_and_complete(self) -> SecurityPostureRecord:
        names = tuple(item.control for item in self.controls)
        if len(names) != len(set(names)):
            raise ValueError("security control checks must be unique")
        if set(names) != set(SecurityControlKind):
            raise ValueError("security posture must cover every required control")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("security finding ids must be unique")
        return self


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2706_MAX_EVIDENCE)


class EvaluateComplexActivitySecurityAccessRequest(FrozenModel):
    """Provisional request bound to the M27-05 search/quant result."""

    operation: Literal["evaluate_complex_activity_security_access"] = M2706_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2706_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    principal: NonEmptyStr
    resource: NonEmptyStr
    action: NonEmptyStr
    policy_version: SemanticVersion
    requested_controls: tuple[SecurityControlKind, ...] = Field(
        min_length=M2706_MAX_CONTROLS, max_length=M2706_MAX_CONTROLS
    )
    consent_reference: ArtifactReference | None = None
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2706_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EvaluateComplexActivitySecurityAccessRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("request id must bind execution context")
        if not self.upstream_result.media_type:
            raise ValueError("request must bind a non-empty upstream media type")
        if len(set(self.requested_controls)) != len(self.requested_controls):
            raise ValueError("requested security controls must be unique")
        if set(self.requested_controls) != set(SecurityControlKind):
            raise ValueError("request must enumerate every required security control")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifact ids must be unique")
        return self


class ComplexActivitySecurityAccessResult(FrozenModel):
    """Access decision, immutable audit event, posture, or safe failure."""

    output_type: Literal["complex_activity_security_access"] = "complex_activity_security_access"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2706_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateComplexActivitySecurityAccessRequest
    status: SecurityAssessmentStatus
    access_decision: AccessDecision | None = None
    audit_event: AuditEvent | None = None
    security_posture: SecurityPostureRecord | None = None
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2706_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2706_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivitySecurityAccessResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is SecurityAssessmentStatus.EVALUATED:
            if (
                self.access_decision is None
                or self.audit_event is None
                or self.security_posture is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires supported security records")
            if (
                self.access_decision.principal != self.request.principal
                or self.access_decision.resource != self.request.resource
                or self.access_decision.action != self.request.action
                or self.access_decision.policy_version != self.request.policy_version
            ):
                raise ValueError("access decision must bind exact request subject and policy")
            if (
                self.audit_event.principal != self.request.principal
                or self.audit_event.resource != self.request.resource
                or self.audit_event.action != self.request.action
                or self.audit_event.timestamp != self.request.context.occurred_at
                or self.audit_event.decision_state is not self.access_decision.state
            ):
                raise ValueError("audit event must bind exact request subject and decision")
        elif (
            self.access_decision is not None
            or self.audit_event is not None
            or self.security_posture is not None
            or self.safe_failure_report is None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2706_CONTRACT_VERSION",
    "M2706_GATE",
    "M2706_M2705_INPUT_MEDIA_TYPE",
    "M2706_MAX_CANONICAL_REQUEST_BYTES",
    "M2706_MAX_CANONICAL_RESULT_BYTES",
    "M2706_MAX_CONTROLS",
    "M2706_MAX_EVIDENCE",
    "M2706_MAX_FINDINGS",
    "M2706_MODULE_ID",
    "M2706_OPERATION",
    "M2706_OUTPUT_MEDIA_TYPE",
    "M2706_OWNER",
    "M2706_PARENT",
    "M2706_PROVISIONAL_ABI",
    "M2706_SAFETY_CLASS",
    "AccessDecision",
    "AccessDecisionState",
    "AuditEvent",
    "ComplexActivitySecurityAccessResult",
    "ControlStatus",
    "EvaluateComplexActivitySecurityAccessRequest",
    "SafeFailureReport",
    "SecurityAssessmentStatus",
    "SecurityControlCheck",
    "SecurityControlKind",
    "SecurityFinding",
    "SecurityFindingCode",
    "SecurityFindingSeverity",
    "SecurityPostureRecord",
    "SecurityPostureStatus",
]
