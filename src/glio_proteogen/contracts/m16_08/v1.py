"""Provisional M16-08 translation monitoring and rollback contracts.

The M16-08 dossier requires usage telemetry, support drift, workflow effects,
discrepancy monitoring, suspension, and rollback. Critical drift or policy
violations must trigger an explicit decision; unsupported cases abstain.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M16-08 dossier slice.
M1608_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-08"
M1608_OPERATION: Final = "monitor_protein_rna_translation_health"
M1608_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1608_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-08+json"
M1608_M1607_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-07+json"
M1608_PARENT: Final = "protein_rna_discordance"
M1608_OWNER: Final = "Data engineering"
M1608_SAFETY_CLASS: Final = "S2"
M1608_GATE: Final = "G5"
M1608_PROVISIONAL_ABI: Final = True
M1608_MAX_SIGNALS: Final = 512
M1608_MAX_ASSESSMENTS: Final = 128
M1608_MAX_TRIGGERS: Final = 64
M1608_MAX_RECOVERY_STEPS: Final = 64
M1608_MAX_EVIDENCE: Final = 64
M1608_MAX_DIAGNOSTICS: Final = 128
M1608_MAX_FINDINGS: Final = 64
M1608_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1608_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1608_EVIDENCE_CLAIM: Final = (
    "Caller-declared M16-08 translation-health and rollback material; issuer "
    "authority is not authenticated."
)


class HealthSignalKind(StrEnum):
    USAGE_TELEMETRY = "usage_telemetry"
    SUPPORT_DRIFT = "support_drift"
    WORKFLOW_EFFECT = "workflow_effect"
    DISCREPANCY = "discrepancy"


class HealthSignalStatus(StrEnum):
    WITHIN_ENVELOPE = "within_envelope"
    DRIFTING = "drifting"
    NOT_EVALUABLE = "not_evaluable"


class TranslationHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    ABSTAINED = "abstained"


class RollbackDecision(StrEnum):
    CONTINUE = "continue"
    SUSPEND = "suspend"
    ROLLBACK = "rollback"
    ABSTAIN = "abstain"


class MonitorDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class MonitorFindingCode(StrEnum):
    CRITICAL_DRIFT = "critical_drift"
    POLICY_VIOLATION = "policy_violation"
    ROLLBACK_REQUIRED = "rollback_required"
    INPUT_INCOMPLETE = "input_incomplete"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class HealthSignal(FrozenModel):
    signal_id: Identifier
    kind: HealthSignalKind
    metric: NonEmptyStr
    observed_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    status: HealthSignalStatus
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1608_MAX_EVIDENCE
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> HealthSignal:
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("health signal bounds must be ordered")
        if self.status is HealthSignalStatus.WITHIN_ENVELOPE:
            if self.lower_bound is None or self.upper_bound is None:
                raise ValueError("within-envelope signals require both bounds")
            if not self.lower_bound <= self.observed_value <= self.upper_bound:
                raise ValueError("within-envelope signal must lie inside its bounds")
        if self.status is HealthSignalStatus.DRIFTING:
            if self.lower_bound is None and self.upper_bound is None:
                raise ValueError("drifting signals require a declared bound")
            if (
                self.lower_bound is not None
                and self.upper_bound is not None
                and self.lower_bound <= self.observed_value <= self.upper_bound
            ):
                raise ValueError("drifting signal cannot lie inside its bounds")
        return self


class DriftAssessment(FrozenModel):
    assessment_id: Identifier
    signal_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M1608_MAX_SIGNALS)
    summary: NonEmptyStr
    status: HealthSignalStatus
    critical: bool = False
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def assessment_is_closed(self) -> DriftAssessment:
        if len(set(self.signal_ids)) != len(self.signal_ids):
            raise ValueError("drift assessment signal ids must be unique")
        if self.critical and self.status is not HealthSignalStatus.DRIFTING:
            raise ValueError("critical drift assessments must be drifting")
        return self


class RollbackPlan(FrozenModel):
    plan_id: Identifier
    trigger_conditions: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1608_MAX_TRIGGERS
    )
    target_version: SemanticVersion
    action: NonEmptyStr
    recovery_steps: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=M1608_MAX_RECOVERY_STEPS
    )
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def rollback_is_recoverable(self) -> RollbackPlan:
        if len(set(self.trigger_conditions)) != len(self.trigger_conditions):
            raise ValueError("rollback trigger conditions must be unique")
        if len(set(self.recovery_steps)) != len(self.recovery_steps):
            raise ValueError("rollback recovery steps must be unique")
        return self


class TranslationMonitoringConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    reference_artifact: ArtifactReference
    monitoring_window: NonEmptyStr
    critical_threshold: NonEmptyStr
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)


class TranslationHealthReport(FrozenModel):
    """Versioned health report with closed signal and rollback references."""

    report_id: Identifier
    version: SemanticVersion
    signals: tuple[HealthSignal, ...] = Field(min_length=1, max_length=M1608_MAX_SIGNALS)
    assessments: tuple[DriftAssessment, ...] = Field(
        min_length=1, max_length=M1608_MAX_ASSESSMENTS
    )
    rollback_plan: RollbackPlan
    configuration: TranslationMonitoringConfiguration
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> TranslationHealthReport:
        signal_ids = tuple(item.signal_id for item in self.signals)
        assessment_ids = tuple(item.assessment_id for item in self.assessments)
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("health signal ids must be unique")
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("drift assessment ids must be unique")
        known = set(signal_ids)
        for assessment in self.assessments:
            if not set(assessment.signal_ids) <= known:
                raise ValueError("drift assessment references an unknown signal")
        return self


class MonitorDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: MonitorDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)


class MonitorProteinRnaTranslationHealthRequest(FrozenModel):
    """Provisional request bound to the M16-07 upstream workflow object."""

    operation: Literal["monitor_protein_rna_translation_health"] = M1608_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1608_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: TranslationMonitoringConfiguration
    signals: tuple[HealthSignal, ...] = Field(min_length=1, max_length=M1608_MAX_SIGNALS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1608_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> MonitorProteinRnaTranslationHealthRequest:
        if self.upstream_result.media_type != M1608_M1607_INPUT_MEDIA_TYPE:
            raise ValueError("monitor request must bind the provisional M16-07 result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("monitor source artifact references must be unique")
        if self.configuration.version != self.upstream_result.version:
            raise ValueError("monitor configuration version must bind the upstream result version")
        return self


class ProteinRnaDiscordanceTranslationHealthResult(FrozenModel):
    """Translation-health state with explicit suspension/rollback decision."""

    output_type: Literal["protein_rna_discordance_translation_health"] = (
        "protein_rna_discordance_translation_health"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1608_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: MonitorProteinRnaTranslationHealthRequest
    health_status: TranslationHealthStatus
    rollback_decision: RollbackDecision
    report: TranslationHealthReport | None = None
    diagnostics: tuple[MonitorDiagnostic, ...] = Field(
        min_length=1, max_length=M1608_MAX_DIAGNOSTICS
    )
    findings: tuple[MonitorFindingCode, ...] = Field(default=(), max_length=M1608_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1608_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1608_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceTranslationHealthResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if len(set(self.findings)) != len(self.findings):
            raise ValueError("monitor findings must be unique")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("monitor diagnostic ids must be unique")
        if self.health_status is TranslationHealthStatus.HEALTHY:
            if (
                self.report is None
                or self.rollback_decision is not RollbackDecision.CONTINUE
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("healthy result requires supported report and continue decision")
        elif self.health_status is TranslationHealthStatus.DEGRADED:
            if (
                self.report is None
                or self.rollback_decision is not RollbackDecision.SUSPEND
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("degraded result requires review and suspension")
        elif self.health_status is TranslationHealthStatus.CRITICAL:
            if (
                self.report is None
                or self.rollback_decision is not RollbackDecision.ROLLBACK
                or self.support_decision.status is not SupportStatus.REVIEW_REQUIRED
                or not self.human_review_required
            ):
                raise ValueError("critical result requires review and rollback")
        elif (
            self.report is not None
            or self.rollback_decision is not RollbackDecision.ABSTAIN
            or self.abstention_reason is None
                or self.support_decision.status
                not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
                or not self.human_review_required
            ):
            raise ValueError("abstained result requires no report and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1608_CONTRACT_VERSION",
    "M1608_EVIDENCE_CLAIM",
    "M1608_GATE",
    "M1608_M1607_INPUT_MEDIA_TYPE",
    "M1608_MAX_ASSESSMENTS",
    "M1608_MAX_CANONICAL_REQUEST_BYTES",
    "M1608_MAX_CANONICAL_RESULT_BYTES",
    "M1608_MAX_DIAGNOSTICS",
    "M1608_MAX_EVIDENCE",
    "M1608_MAX_FINDINGS",
    "M1608_MAX_RECOVERY_STEPS",
    "M1608_MAX_SIGNALS",
    "M1608_MAX_TRIGGERS",
    "M1608_MODULE_ID",
    "M1608_OPERATION",
    "M1608_OUTPUT_MEDIA_TYPE",
    "M1608_OWNER",
    "M1608_PARENT",
    "M1608_PROVISIONAL_ABI",
    "M1608_SAFETY_CLASS",
    "DriftAssessment",
    "HealthSignal",
    "HealthSignalKind",
    "HealthSignalStatus",
    "MonitorDiagnostic",
    "MonitorDiagnosticStatus",
    "MonitorFindingCode",
    "MonitorProteinRnaTranslationHealthRequest",
    "ProteinRnaDiscordanceTranslationHealthResult",
    "RollbackDecision",
    "RollbackPlan",
    "TranslationHealthReport",
    "TranslationHealthStatus",
    "TranslationMonitoringConfiguration",
]
