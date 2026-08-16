"""Provisional M26-05 observability and telemetry contracts.

The dossier requires input-quality, model-behavior, uncertainty, abstention,
drift, latency, error, resource, and reviewer-action signals. This scaffold
keeps critical signals retained and auditable while unresolved support safely
abstains.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m26_05.canonical import (
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
# lines 9212-9252. Owner confirmation and implementation details remain
# pending.
M2605_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-05"
M2605_OPERATION: Final = "emit_proteomics_observability_telemetry"
M2605_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2605_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-05+json"
M2605_M2604_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-04+json"
M2605_PARENT: Final = "protein subtype"
M2605_OWNER: Final = "Clinical science"
M2605_SAFETY_CLASS: Final = "S3"
M2605_GATE: Final = "G4"
M2605_PROVISIONAL_ABI: Final = True
M2605_MAX_SAMPLES: Final = 512
M2605_MAX_DASHBOARDS: Final = 32
M2605_MAX_REVIEWER_ACTIONS: Final = 64
M2605_MAX_EVIDENCE: Final = 64
M2605_MAX_FINDINGS: Final = 64
M2605_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2605_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class TelemetryMetricKind(StrEnum):
    INPUT_QUALITY = "input_quality"
    MODEL_BEHAVIOR = "model_behavior"
    UNCERTAINTY = "uncertainty"
    ABSTENTION = "abstention"
    DRIFT = "drift"
    LATENCY = "latency"
    ERRORS = "errors"
    RESOURCES = "resources"
    REVIEWER_ACTIONS = "reviewer_actions"


class TelemetryUnit(StrEnum):
    SCORE = "score"
    COUNT = "count"
    MILLISECONDS = "milliseconds"
    BYTES = "bytes"
    RATIO = "ratio"


class AlertState(StrEnum):
    CLEAR = "clear"
    OPEN = "open"
    SUPPRESSED = "suppressed"
    NOT_EVALUABLE = "not_evaluable"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReviewerActionKind(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    OVERRIDDEN = "overridden"
    RELEASED = "released"
    ROLLED_BACK = "rolled_back"


class TelemetryStatus(StrEnum):
    EMITTED = "emitted"
    ABSTAINED = "abstained"


class TelemetryFindingCode(StrEnum):
    CRITICAL_SIGNAL_MISSING = "critical_signal_missing"
    DRIFT_DETECTED = "drift_detected"
    ERROR_BUDGET_EXCEEDED = "error_budget_exceeded"
    REVIEWER_ACTION_REQUIRED = "reviewer_action_required"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class TelemetrySample(FrozenModel):
    sample_id: Identifier
    metric: TelemetryMetricKind
    value: float = Field(allow_inf_nan=False)
    unit: TelemetryUnit
    observed_at: AwareDatetime
    source: NonEmptyStr
    retained: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_and_unit_are_closed(self) -> TelemetrySample:
        if not isfinite(self.value):
            raise ValueError("telemetry sample values must be finite")
        allowed_units = {
            TelemetryMetricKind.INPUT_QUALITY: {TelemetryUnit.SCORE, TelemetryUnit.RATIO},
            TelemetryMetricKind.MODEL_BEHAVIOR: {TelemetryUnit.SCORE, TelemetryUnit.RATIO},
            TelemetryMetricKind.UNCERTAINTY: {TelemetryUnit.SCORE, TelemetryUnit.RATIO},
            TelemetryMetricKind.ABSTENTION: {TelemetryUnit.COUNT, TelemetryUnit.RATIO},
            TelemetryMetricKind.DRIFT: {TelemetryUnit.SCORE, TelemetryUnit.RATIO},
            TelemetryMetricKind.LATENCY: {TelemetryUnit.MILLISECONDS},
            TelemetryMetricKind.ERRORS: {TelemetryUnit.COUNT, TelemetryUnit.RATIO},
            TelemetryMetricKind.RESOURCES: {TelemetryUnit.COUNT, TelemetryUnit.BYTES},
            TelemetryMetricKind.REVIEWER_ACTIONS: {TelemetryUnit.COUNT},
        }
        if self.unit not in allowed_units[self.metric]:
            raise ValueError("telemetry metric and unit are incompatible")
        return self


class DashboardDefinition(FrozenModel):
    dashboard_id: Identifier
    title: NonEmptyStr
    metrics: tuple[TelemetryMetricKind, ...] = Field(min_length=1, max_length=9)
    owner: NonEmptyStr
    refresh_seconds: int = Field(ge=1)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def metrics_are_unique(self) -> DashboardDefinition:
        if len(set(self.metrics)) != len(self.metrics):
            raise ValueError("dashboard metrics must be unique")
        return self


class AlertRecord(FrozenModel):
    alert_id: Identifier
    state: AlertState
    severity: AlertSeverity
    metric: TelemetryMetricKind
    message: NonEmptyStr
    triggered_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def alert_times_are_closed(self) -> AlertRecord:
        if self.state in {AlertState.OPEN, AlertState.SUPPRESSED} and self.triggered_at is None:
            raise ValueError("open or suppressed alerts require triggered_at")
        if self.resolved_at is not None:
            if self.triggered_at is None or self.resolved_at < self.triggered_at:
                raise ValueError("resolved_at must follow triggered_at")
            if self.state not in {AlertState.CLEAR, AlertState.NOT_EVALUABLE}:
                raise ValueError("resolved alerts must be clear or not_evaluable")
        if self.state is AlertState.NOT_EVALUABLE and self.severity is AlertSeverity.CRITICAL:
            raise ValueError("not-evaluable alerts cannot claim critical severity")
        return self


class ReviewerActionRecord(FrozenModel):
    action_id: Identifier
    kind: ReviewerActionKind
    reviewer: NonEmptyStr
    target_id: Identifier
    occurred_at: AwareDatetime
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)


class TelemetryFinding(FrozenModel):
    finding_id: Identifier
    code: TelemetryFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2605_MAX_EVIDENCE)


class TelemetryStream(FrozenModel):
    stream_id: Identifier
    version: SemanticVersion
    samples: tuple[TelemetrySample, ...] = Field(min_length=1, max_length=M2605_MAX_SAMPLES)
    reviewer_actions: tuple[ReviewerActionRecord, ...] = Field(
        default=(), max_length=M2605_MAX_REVIEWER_ACTIONS
    )
    findings: tuple[TelemetryFinding, ...] = Field(default=(), max_length=M2605_MAX_FINDINGS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def samples_are_unique(self) -> TelemetryStream:
        sample_ids = tuple(item.sample_id for item in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("telemetry sample ids must be unique")
        action_ids = tuple(item.action_id for item in self.reviewer_actions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("reviewer action ids must be unique")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("telemetry finding ids must be unique")
        observed = tuple(item.observed_at for item in self.samples)
        if observed != tuple(sorted(observed)):
            raise ValueError("telemetry samples must be ordered by observed_at")
        return self


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)


class EmitProteomicsTelemetryRequest(FrozenModel):
    """Provisional request bound to the M26-04 standards-registry result."""

    operation: Literal["emit_proteomics_observability_telemetry"] = M2605_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2605_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    requested_metrics: tuple[TelemetryMetricKind, ...] = Field(min_length=1, max_length=9)
    samples: tuple[TelemetrySample, ...] = Field(min_length=1, max_length=M2605_MAX_SAMPLES)
    reviewer_actions: tuple[ReviewerActionRecord, ...] = Field(
        default=(), max_length=M2605_MAX_REVIEWER_ACTIONS
    )
    dashboard_definitions: tuple[DashboardDefinition, ...] = Field(
        min_length=1, max_length=M2605_MAX_DASHBOARDS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2605_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EmitProteomicsTelemetryRequest:
        if self.upstream_result.media_type != M2605_M2604_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M26-04 registry result")
        if len(set(self.requested_metrics)) != len(self.requested_metrics):
            raise ValueError("requested telemetry metrics must be unique")
        if self.upstream_result not in self.source_artifacts:
            raise ValueError("upstream result must be included in source artifacts")
        dashboard_ids = tuple(item.dashboard_id for item in self.dashboard_definitions)
        if len(dashboard_ids) != len(set(dashboard_ids)):
            raise ValueError("dashboard ids must be unique")
        requested = set(self.requested_metrics)
        if any(not set(item.metrics).issubset(requested) for item in self.dashboard_definitions):
            raise ValueError("dashboard metrics must be requested telemetry metrics")
        sample_ids = tuple(item.sample_id for item in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("request telemetry sample ids must be unique")
        sample_times = tuple(item.observed_at for item in self.samples)
        if sample_times != tuple(sorted(sample_times)):
            raise ValueError("request telemetry samples must be ordered by observed_at")
        action_ids = tuple(item.action_id for item in self.reviewer_actions)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("request reviewer action ids must be unique")
        return self


class ProteomicsTelemetryResult(FrozenModel):
    """Telemetry stream, dashboards, alert state, or explicit safe failure."""

    output_type: Literal["proteomics_observability_telemetry"] = (
        "proteomics_observability_telemetry"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2605_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EmitProteomicsTelemetryRequest
    status: TelemetryStatus
    telemetry_stream: TelemetryStream | None = None
    dashboards: tuple[DashboardDefinition, ...] = Field(default=(), max_length=M2605_MAX_DASHBOARDS)
    alert: AlertRecord | None = None
    findings: tuple[TelemetryFinding, ...] = Field(default=(), max_length=M2605_MAX_FINDINGS)
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2605_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2605_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteomicsTelemetryResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        dashboard_ids = tuple(item.dashboard_id for item in self.dashboards)
        if len(dashboard_ids) != len(set(dashboard_ids)):
            raise ValueError("result dashboard ids must be unique")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        if self.status is TelemetryStatus.EMITTED:
            if (
                self.telemetry_stream is None
                or not self.dashboards
                or self.alert is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("emitted result requires supported telemetry records")
            sample_metrics = {sample.metric for sample in self.telemetry_stream.samples}
            if not set(self.request.requested_metrics).issubset(sample_metrics):
                raise ValueError("emitted stream must cover every requested metric")
            if (
                self.alert.state in {AlertState.OPEN, AlertState.SUPPRESSED}
                and not self.human_review_required
            ):
                raise ValueError("open or suppressed alerts require human review")
        elif (
            self.telemetry_stream is not None
            or self.dashboards
            or self.alert is not None
            or self.safe_failure_report is None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2605_CONTRACT_VERSION",
    "M2605_GATE",
    "M2605_M2604_INPUT_MEDIA_TYPE",
    "M2605_MAX_CANONICAL_REQUEST_BYTES",
    "M2605_MAX_CANONICAL_RESULT_BYTES",
    "M2605_MAX_DASHBOARDS",
    "M2605_MAX_EVIDENCE",
    "M2605_MAX_FINDINGS",
    "M2605_MAX_REVIEWER_ACTIONS",
    "M2605_MAX_SAMPLES",
    "M2605_MODULE_ID",
    "M2605_OPERATION",
    "M2605_OUTPUT_MEDIA_TYPE",
    "M2605_OWNER",
    "M2605_PARENT",
    "M2605_PROVISIONAL_ABI",
    "M2605_SAFETY_CLASS",
    "AlertRecord",
    "AlertSeverity",
    "AlertState",
    "DashboardDefinition",
    "EmitProteomicsTelemetryRequest",
    "ProteomicsTelemetryResult",
    "ReviewerActionKind",
    "ReviewerActionRecord",
    "SafeFailureReport",
    "TelemetryFinding",
    "TelemetryFindingCode",
    "TelemetryMetricKind",
    "TelemetrySample",
    "TelemetryStatus",
    "TelemetryStream",
    "TelemetryUnit",
]
