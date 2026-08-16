"""Provisional M26-06 security, privacy, and access-control contracts.

The dossier calls for least privilege, encryption, secrets, isolation,
consent, de-identification, audit, and threat detection. This scaffold keeps
those controls typed and auditable while making unresolved support abstain.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m26_06.canonical import (
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
# lines 9256-9296. Owner confirmation and implementation details remain
# pending.
M2606_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-06"
M2606_DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
M2606_DOSSIER_SLICE: Final = "source-manifest.yaml:9256-9296"
M2606_OPERATION: Final = "evaluate_proteomics_security_access"
M2606_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2606_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-06+json"
M2606_M2605_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-05+json"
M2606_PARENT: Final = "protein subtype"
M2606_OWNER: Final = "Data engineering"
M2606_SAFETY_CLASS: Final = "S3"
M2606_GATE: Final = "G4"
M2606_PROVISIONAL_ABI: Final = True
M2606_MAX_EVIDENCE: Final = 64
M2606_MAX_FINDINGS: Final = 64
M2606_MAX_CONTROLS: Final = 8
M2606_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2606_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)

    @model_validator(mode="after")
    def failed_checks_are_explainable(self) -> SecurityControlCheck:
        """Every non-passing control must remain actionable and reviewable."""

        if self.status is not ControlStatus.PASSED and not self.rationale:
            raise ValueError("non-passing controls require a review rationale")
        return self


class SecurityControlDeclaration(FrozenModel):
    """Caller-declared evidence for one security control.

    M26-06 never inspects protected data or claims to certify a control from an
    opaque payload.  Declarations are therefore explicit, evidence-linked, and
    carried into the posture and provenance records unchanged.
    """

    control: SecurityControlKind
    status: ControlStatus
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)

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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)


class SecurityFinding(FrozenModel):
    finding_id: Identifier
    code: SecurityFindingCode
    severity: SecurityFindingSeverity
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)

    @model_validator(mode="after")
    def severe_findings_cannot_be_unreferenced(self) -> SecurityFinding:
        if (
            self.severity
            in {
                SecurityFindingSeverity.ERROR,
                SecurityFindingSeverity.CRITICAL,
            }
            and not self.evidence
        ):
            raise ValueError("severe security findings require evidence")
        return self


class SecurityPostureRecord(FrozenModel):
    posture_id: Identifier
    version: SemanticVersion
    status: SecurityPostureStatus
    controls: tuple[SecurityControlCheck, ...] = Field(
        min_length=M2606_MAX_CONTROLS, max_length=M2606_MAX_CONTROLS
    )
    findings: tuple[SecurityFinding, ...] = Field(default=(), max_length=M2606_MAX_FINDINGS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)

    @model_validator(mode="after")
    def controls_are_unique_and_complete(self) -> SecurityPostureRecord:
        names = tuple(item.control for item in self.controls)
        if len(names) != len(set(names)):
            raise ValueError("security control checks must be unique")
        if set(names) != set(SecurityControlKind):
            raise ValueError("security posture must cover every required control")
        statuses = {item.status for item in self.controls}
        if self.status is SecurityPostureStatus.COMPLIANT and statuses != {ControlStatus.PASSED}:
            raise ValueError("compliant posture requires every control to pass")
        if self.status is SecurityPostureStatus.CRITICAL and ControlStatus.FAILED not in statuses:
            raise ValueError("critical posture requires a failed control")
        if self.status is SecurityPostureStatus.NOT_EVALUABLE and not (
            statuses & {ControlStatus.NOT_EVALUABLE, ControlStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("not-evaluable posture requires unresolved control evidence")
        return self


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)


class EvaluateProteomicsSecurityAccessRequest(FrozenModel):
    """Provisional request bound to the M26-05 standards-registry result."""

    operation: Literal["evaluate_proteomics_security_access"] = M2606_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2606_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    principal: NonEmptyStr
    resource: NonEmptyStr
    action: NonEmptyStr
    policy_version: SemanticVersion
    requested_controls: tuple[SecurityControlKind, ...] = Field(
        min_length=M2606_MAX_CONTROLS, max_length=M2606_MAX_CONTROLS
    )
    control_declarations: tuple[SecurityControlDeclaration, ...] = Field(
        min_length=M2606_MAX_CONTROLS, max_length=M2606_MAX_CONTROLS
    )
    consent_reference: ArtifactReference | None = None
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2606_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EvaluateProteomicsSecurityAccessRequest:
        if self.upstream_result.media_type != M2606_M2605_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M26-05 standards result")
        if len(set(self.requested_controls)) != len(self.requested_controls):
            raise ValueError("requested security controls must be unique")
        if set(self.requested_controls) != set(SecurityControlKind):
            raise ValueError("request must declare every required security control exactly once")
        declared = tuple(item.control for item in self.control_declarations)
        if len(set(declared)) != len(declared):
            raise ValueError("security control declarations must be unique")
        if set(declared) != set(SecurityControlKind):
            raise ValueError("control declarations must cover every required security control")
        if set(declared) != set(self.requested_controls):
            raise ValueError("requested controls and declarations must match")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request ID must match request ID")
        return self


class ProteomicsSecurityAccessResult(FrozenModel):
    """Access decision, immutable audit event, posture, or safe failure."""

    output_type: Literal["proteomics_security_access"] = "proteomics_security_access"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2606_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateProteomicsSecurityAccessRequest
    status: SecurityAssessmentStatus
    access_decision: AccessDecision | None = None
    audit_event: AuditEvent | None = None
    security_posture: SecurityPostureRecord | None = None
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2606_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2606_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteomicsSecurityAccessResult:
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
        if self.status is SecurityAssessmentStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstained security assessments require human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2606_CONTRACT_VERSION",
    "M2606_DOSSIER_SHA256",
    "M2606_DOSSIER_SLICE",
    "M2606_GATE",
    "M2606_M2605_INPUT_MEDIA_TYPE",
    "M2606_MAX_CANONICAL_REQUEST_BYTES",
    "M2606_MAX_CANONICAL_RESULT_BYTES",
    "M2606_MAX_CONTROLS",
    "M2606_MAX_EVIDENCE",
    "M2606_MAX_FINDINGS",
    "M2606_MODULE_ID",
    "M2606_OPERATION",
    "M2606_OUTPUT_MEDIA_TYPE",
    "M2606_OWNER",
    "M2606_PARENT",
    "M2606_PROVISIONAL_ABI",
    "M2606_SAFETY_CLASS",
    "AccessDecision",
    "AccessDecisionState",
    "AuditEvent",
    "ControlStatus",
    "EvaluateProteomicsSecurityAccessRequest",
    "ProteomicsSecurityAccessResult",
    "SafeFailureReport",
    "SecurityAssessmentStatus",
    "SecurityControlCheck",
    "SecurityControlDeclaration",
    "SecurityControlKind",
    "SecurityFinding",
    "SecurityFindingCode",
    "SecurityFindingSeverity",
    "SecurityPostureRecord",
    "SecurityPostureStatus",
]
