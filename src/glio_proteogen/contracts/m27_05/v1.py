"""Provisional M27-05 Search/quant observability and telemetry contracts.

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

from glio_proteogen.contracts.m27_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
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
# lines 9572-9612. Owner confirmation and implementation details remain
# pending.
M2605_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-05"
M2605_OPERATION: Final = "emit_search_quant_observability_telemetry"
M2605_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2605_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-05+json"
M2605_M2604_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-04+json"
M2605_PARENT: Final = "complex activity"
M2605_OWNER: Final = "Data engineering"
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

# M27-05 public names. The M2605-prefixed aliases above are retained only as
# local template compatibility while this inferred ABI remains provisional.
M2705_MODULE_ID: Final = M2605_MODULE_ID
M2705_OPERATION: Final = M2605_OPERATION
M2705_CONTRACT_VERSION: Final = M2605_CONTRACT_VERSION
M2705_OUTPUT_MEDIA_TYPE: Final = M2605_OUTPUT_MEDIA_TYPE
M2705_M2704_INPUT_MEDIA_TYPE: Final = M2605_M2604_INPUT_MEDIA_TYPE
M2705_PARENT: Final = M2605_PARENT
M2705_OWNER: Final = M2605_OWNER
M2705_SAFETY_CLASS: Final = M2605_SAFETY_CLASS
M2705_GATE: Final = M2605_GATE
M2705_PROVISIONAL_ABI: Final = M2605_PROVISIONAL_ABI
M2705_MAX_SAMPLES: Final = M2605_MAX_SAMPLES
M2705_MAX_DASHBOARDS: Final = M2605_MAX_DASHBOARDS
M2705_MAX_REVIEWER_ACTIONS: Final = M2605_MAX_REVIEWER_ACTIONS
M2705_MAX_EVIDENCE: Final = M2605_MAX_EVIDENCE
M2705_MAX_FINDINGS: Final = M2605_MAX_FINDINGS
M2705_MAX_CANONICAL_REQUEST_BYTES: Final = M2605_MAX_CANONICAL_REQUEST_BYTES
M2705_MAX_CANONICAL_RESULT_BYTES: Final = M2605_MAX_CANONICAL_RESULT_BYTES


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
    value: float
    unit: TelemetryUnit
    observed_at: AwareDatetime
    source: NonEmptyStr
    retained: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2605_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_is_finite(self) -> TelemetrySample:
        if not isfinite(self.value):
            raise ValueError("telemetry sample values must be finite")
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
    def resolution_is_chronological(self) -> AlertRecord:
        if (
            self.resolved_at is not None
            and self.triggered_at is not None
            and self.resolved_at < self.triggered_at
        ):
            raise ValueError("alert resolution cannot precede trigger time")
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
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("telemetry finding ids must be unique")
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
    """Provisional request bound to the M27-04 gateway result."""

    operation: Literal["emit_search_quant_observability_telemetry"] = M2605_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2605_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    requested_metrics: tuple[TelemetryMetricKind, ...] = Field(min_length=1, max_length=9)
    dashboard_definitions: tuple[DashboardDefinition, ...] = Field(
        min_length=1, max_length=M2605_MAX_DASHBOARDS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2605_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EmitProteomicsTelemetryRequest:
        if not self.upstream_result.media_type:
            raise ValueError("request must bind a non-empty upstream media type")
        if len(set(self.requested_metrics)) != len(self.requested_metrics):
            raise ValueError("requested telemetry metrics must be unique")
        dashboard_ids = tuple(item.dashboard_id for item in self.dashboard_definitions)
        if len(dashboard_ids) != len(set(dashboard_ids)):
            raise ValueError("dashboard ids must be unique")
        return self


class ProteomicsTelemetryResult(FrozenModel):
    """Telemetry stream, dashboards, alert state, or explicit safe failure."""

    output_type: Literal["search_quant_observability_telemetry"] = (
        "search_quant_observability_telemetry"
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
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2605_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2605_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    def _provenance_is_closed(self) -> None:
        references = self.request.context.references
        expected_controls = tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=getattr(decision, "binding_digest", None),
            )
            for role, decision in (
                (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
                (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
                (ControlRole.PROVENANCE, references.provenance),
                (ControlRole.CONSENT, references.consent),
                (ControlRole.QUALITY, references.quality),
                (ControlRole.SUPPORT, references.support),
                (ControlRole.INTENDED_USE, references.intended_use),
            )
        )
        provenance_bindings = (
            (
                self.provenance.activity_id,
                "m2705.activity." + self.request_digest.removeprefix("sha256:"),
                "activity identity",
            ),
            (self.provenance.actor_id, self.request.context.actor_id, "actor identity"),
            (self.provenance.module_id, M2705_MODULE_ID, "module identity"),
            (self.provenance.module_version, M2705_CONTRACT_VERSION, "module version"),
            (self.provenance.generated_at, self.request.context.occurred_at, "generated time"),
            (
                self.provenance.input_digests,
                tuple(item.digest for item in self.request.source_artifacts),
                "input digests",
            ),
            (
                self.provenance.configuration_digest,
                self.request.upstream_result.digest,
                "configuration digest",
            ),
            (
                self.provenance.consent_decision_id,
                references.consent.decision_id,
                "consent decision",
            ),
            (self.provenance.consent_state, references.consent.state, "consent state"),
            (
                self.provenance.consent_policy_version,
                references.consent.policy_version,
                "consent policy version",
            ),
            (
                self.provenance.consent_evidence_digest,
                references.consent.evidence.digest,
                "consent evidence",
            ),
            (self.provenance.control_decisions, expected_controls, "control decisions"),
        )
        for actual, expected, label in provenance_bindings:
            if actual != expected:
                raise ValueError(f"provenance {label} does not bind the request")

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteomicsTelemetryResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = "m2705.result." + self.request_digest.removeprefix("sha256:")
        if self.result_id != expected_result_id:
            raise ValueError("result id does not bind the exact request digest")
        self._provenance_is_closed()
        if self.status is TelemetryStatus.EMITTED:
            stream = self.telemetry_stream
            alert = self.alert
            if (
                stream is None
                or not self.dashboards
                or alert is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("emitted result requires supported telemetry records")
            if stream.stream_id != f"m2705.stream.{self.request.request_id}":
                raise ValueError("emitted telemetry stream id does not bind the request")
            if tuple(sample.metric for sample in stream.samples) != self.request.requested_metrics:
                raise ValueError("emitted telemetry samples do not bind requested metrics")
            if self.dashboards != self.request.dashboard_definitions:
                raise ValueError("emitted dashboards do not bind the request definitions")
            if stream.evidence != self.evidence:
                raise ValueError("emitted telemetry evidence does not bind the result evidence")
            if alert.alert_id != f"m2705.alert.{self.request.request_id}":
                raise ValueError("emitted alert id does not bind the request")
            if alert.metric != self.request.requested_metrics[0]:
                raise ValueError("emitted alert metric does not bind requested metrics")
        elif (
            self.telemetry_stream is not None
            or self.dashboards
            or self.alert is not None
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
    "M2705_CONTRACT_VERSION",
    "M2705_GATE",
    "M2705_M2704_INPUT_MEDIA_TYPE",
    "M2705_MAX_CANONICAL_REQUEST_BYTES",
    "M2705_MAX_CANONICAL_RESULT_BYTES",
    "M2705_MAX_DASHBOARDS",
    "M2705_MAX_EVIDENCE",
    "M2705_MAX_FINDINGS",
    "M2705_MAX_REVIEWER_ACTIONS",
    "M2705_MAX_SAMPLES",
    "M2705_MODULE_ID",
    "M2705_OPERATION",
    "M2705_OUTPUT_MEDIA_TYPE",
    "M2705_OWNER",
    "M2705_PARENT",
    "M2705_PROVISIONAL_ABI",
    "M2705_SAFETY_CLASS",
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
