"""Provisional M18-08 translation monitoring and rollback contracts.

M18-08 owns usage telemetry, support drift, workflow effects, discrepancies,
suspension, and rollback beneath the biomarker panel projection.  This ABI is
provisional pending Platform engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m18_08.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 6464-6504.
M1808_MODULE_ID: Final = "GLIO-PROTEOGEN-M18-08"
M1808_OPERATION: Final = "monitor_biomarker_panel_translation_health"
M1808_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1808_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-08+json"
M1808_M1807_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m18-07+json"
M1808_PARENT: Final = "biomarker panel"
M1808_OWNER: Final = "Scientific engineering"
M1808_SAFETY_CLASS: Final = "S2"
M1808_GATE: Final = "G5"
M1808_PROVISIONAL_ABI: Final = True
M1808_MAX_TELEMETRY: Final = 256
M1808_MAX_SUPPORT_DRIFT: Final = 128
M1808_MAX_WORKFLOW_EFFECTS: Final = 128
M1808_MAX_DISCREPANCIES: Final = 128
M1808_MAX_EVIDENCE: Final = 64
M1808_MAX_FINDINGS: Final = 64
M1808_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1808_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1808_EVIDENCE_CLAIM: Final = (
    "Caller-declared M18-08 telemetry, support drift, workflow, discrepancy, "
    "suspension and rollback material; issuer authority is not authenticated."
)


class ObservationStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class TranslationHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    ROLLBACK_REQUIRED = "rollback_required"
    NOT_EVALUABLE = "not_evaluable"


class RollbackDecision(StrEnum):
    NONE = "none"
    SUSPEND = "suspend"
    ROLLBACK = "rollback"
    REVIEW_REQUIRED = "review_required"


class MonitorStatus(StrEnum):
    MONITORED = "monitored"
    ABSTAINED = "abstained"


class TranslationFindingCode(StrEnum):
    CRITICAL_DRIFT = "critical_drift"
    POLICY_VIOLATION = "policy_violation"
    SUPPORT_DRIFT = "support_drift"
    WORKFLOW_EFFECT = "workflow_effect"
    DISCREPANCY_UNRESOLVED = "discrepancy_unresolved"
    ROLLBACK_REQUIRED = "rollback_required"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class TelemetryObservation(FrozenModel):
    observation_id: Identifier
    metric_name: NonEmptyStr
    observed_value: float
    baseline_value: float
    allowed_delta: float = Field(ge=0.0)
    status: ObservationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)

    @model_validator(mode="after")
    def finite_measurements(self) -> TelemetryObservation:
        if not all(
            isfinite(value)
            for value in (self.observed_value, self.baseline_value, self.allowed_delta)
        ):
            raise ValueError("telemetry measurements must be finite")
        return self


class SupportDriftObservation(FrozenModel):
    observation_id: Identifier
    support_dimension: NonEmptyStr
    baseline_status: NonEmptyStr
    current_status: NonEmptyStr
    status: ObservationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)


class WorkflowEffectObservation(FrozenModel):
    observation_id: Identifier
    workflow: NonEmptyStr
    effect_description: NonEmptyStr
    status: ObservationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)


class DiscrepancyObservation(FrozenModel):
    discrepancy_id: Identifier
    description: NonEmptyStr
    resolved: bool
    status: ObservationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)


class RollbackPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    critical_failure_threshold: int = Field(ge=1)
    rollback_target_version: SemanticVersion
    rollback_artifact: ArtifactReference
    suspension_reason: NonEmptyStr
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)


class TranslationHealthReport(FrozenModel):
    """Translation health and release decision reconstructed from observations."""

    report_id: Identifier
    version: SemanticVersion
    telemetry: tuple[TelemetryObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_TELEMETRY
    )
    support_drift: tuple[SupportDriftObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_SUPPORT_DRIFT
    )
    workflow_effects: tuple[WorkflowEffectObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_WORKFLOW_EFFECTS
    )
    discrepancies: tuple[DiscrepancyObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_DISCREPANCIES
    )
    health_state: TranslationHealthState
    rollback_decision: RollbackDecision
    rollback_policy: RollbackPolicy
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1808_MAX_EVIDENCE)

    @model_validator(mode="after")
    def decision_matches_state(self) -> TranslationHealthReport:
        required_decisions = {
            TranslationHealthState.HEALTHY: RollbackDecision.NONE,
            TranslationHealthState.DEGRADED: RollbackDecision.REVIEW_REQUIRED,
            TranslationHealthState.SUSPENDED: RollbackDecision.SUSPEND,
            TranslationHealthState.ROLLBACK_REQUIRED: RollbackDecision.ROLLBACK,
            TranslationHealthState.NOT_EVALUABLE: RollbackDecision.REVIEW_REQUIRED,
        }
        required = required_decisions.get(self.health_state)
        if self.rollback_decision is not required:
            raise ValueError("rollback decision must match declared health state")
        observation_ids = (
            tuple(item.observation_id for item in self.telemetry)
            + tuple(item.observation_id for item in self.support_drift)
            + tuple(item.observation_id for item in self.workflow_effects)
        )
        discrepancy_ids = tuple(item.discrepancy_id for item in self.discrepancies)
        all_ids = observation_ids + discrepancy_ids
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("health observation ids must be unique")
        if len(discrepancy_ids) != len(set(discrepancy_ids)):
            raise ValueError("discrepancy observation ids must be unique")
        return self


class TranslationFinding(FrozenModel):
    finding_id: Identifier
    code: TranslationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1808_MAX_EVIDENCE)


class MonitorBiomarkerPanelTranslationHealthRequest(FrozenModel):
    """Provisional request bound to the M18-07 downstream typed export."""

    operation: Literal["monitor_biomarker_panel_translation_health"] = M1808_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1808_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    telemetry: tuple[TelemetryObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_TELEMETRY
    )
    support_drift: tuple[SupportDriftObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_SUPPORT_DRIFT
    )
    workflow_effects: tuple[WorkflowEffectObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_WORKFLOW_EFFECTS
    )
    discrepancies: tuple[DiscrepancyObservation, ...] = Field(
        min_length=1, max_length=M1808_MAX_DISCREPANCIES
    )
    rollback_policy: RollbackPolicy
    support_decision: SupportDecision
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1808_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> MonitorBiomarkerPanelTranslationHealthRequest:
        if self.upstream_result.media_type != M1808_M1807_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M18-07 export result")
        artifact_ids = tuple(artifact.artifact_id for artifact in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("request source artifacts must be unique")
        source_ids = set(artifact_ids)
        if self.upstream_result.artifact_id not in source_ids:
            raise ValueError("upstream result must be listed in source artifacts")
        if self.rollback_policy.rollback_artifact.artifact_id not in source_ids:
            raise ValueError("rollback artifact must be listed in source artifacts")
        evidence_ids = {
            evidence.reference.artifact_id
            for item in (
                *self.telemetry,
                *self.support_drift,
                *self.workflow_effects,
                *self.discrepancies,
                self.rollback_policy,
            )
            for evidence in item.evidence
        }
        if not evidence_ids <= source_ids:
            raise ValueError("monitor evidence references an unknown source artifact")
        return self


class BiomarkerPanelTranslationMonitoringResult(FrozenModel):
    """Translation-health decision with explicit safe quarantine/abstention."""

    output_type: Literal["biomarker_panel_translation_monitoring"] = (
        "biomarker_panel_translation_monitoring"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1808_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: MonitorBiomarkerPanelTranslationHealthRequest
    status: MonitorStatus
    health_report: TranslationHealthReport | None = None
    findings: tuple[TranslationFinding, ...] = Field(default=(), max_length=M1808_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M1808_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1808_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelTranslationMonitoringResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is MonitorStatus.MONITORED:
            if (
                self.health_report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("monitored result requires a supported health report")
        elif (
            self.health_report is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no report and safe status")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        finding_codes = tuple(finding.code for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("translation finding ids must be unique")
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("translation finding codes must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1808_CONTRACT_VERSION",
    "M1808_EVIDENCE_CLAIM",
    "M1808_GATE",
    "M1808_M1807_INPUT_MEDIA_TYPE",
    "M1808_MAX_CANONICAL_REQUEST_BYTES",
    "M1808_MAX_CANONICAL_RESULT_BYTES",
    "M1808_MAX_DISCREPANCIES",
    "M1808_MAX_EVIDENCE",
    "M1808_MAX_FINDINGS",
    "M1808_MAX_SUPPORT_DRIFT",
    "M1808_MAX_TELEMETRY",
    "M1808_MAX_WORKFLOW_EFFECTS",
    "M1808_MODULE_ID",
    "M1808_OPERATION",
    "M1808_OUTPUT_MEDIA_TYPE",
    "M1808_OWNER",
    "M1808_PARENT",
    "M1808_PROVISIONAL_ABI",
    "M1808_SAFETY_CLASS",
    "BiomarkerPanelTranslationMonitoringResult",
    "DiscrepancyObservation",
    "MonitorBiomarkerPanelTranslationHealthRequest",
    "MonitorStatus",
    "ObservationStatus",
    "RollbackDecision",
    "RollbackPolicy",
    "SupportDriftObservation",
    "TelemetryObservation",
    "TranslationFinding",
    "TranslationFindingCode",
    "TranslationHealthReport",
    "TranslationHealthState",
    "WorkflowEffectObservation",
]
