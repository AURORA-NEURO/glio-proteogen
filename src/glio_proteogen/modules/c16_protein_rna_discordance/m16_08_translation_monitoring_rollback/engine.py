"""Deterministic, authorization-first M16-08 monitoring and rollback engine."""

# Keep safety branches explicit and readable for audit review.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_08 import (
    M1608_CONTRACT_VERSION,
    M1608_MODULE_ID,
    DriftAssessment,
    HealthSignal,
    HealthSignalKind,
    HealthSignalStatus,
    MonitorDiagnostic,
    MonitorDiagnosticStatus,
    MonitorFindingCode,
    MonitorProteinRnaTranslationHealthRequest,
    ProteinRnaDiscordanceTranslationHealthResult,
    RollbackDecision,
    RollbackPlan,
    TranslationHealthReport,
    TranslationHealthStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorProteinRnaTranslationHealthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceTranslationHealthResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1608AuthorizationError(PermissionError):
    """Caller controls do not authorize translation-health monitoring."""

    def __init__(self) -> None:
        super().__init__(
            "M16-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1608ReplayVerificationError(ValueError):
    """A monitoring result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M16-08 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1608_authorization(candidate: object) -> None:
    """Check all seven controls before traversing monitoring signals."""

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
        raise M1608AuthorizationError from None
    if states != expected:
        raise M1608AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1608_authorization(candidate)
    return candidate


def _evidence(request: MonitorProteinRnaTranslationHealthRequest) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        request.configuration.reference_artifact,
        *request.source_artifacts,
        *[item.reference for item in request.configuration.evidence],
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
            claim="Caller-declared M16-08 translation-health, rollback, and control evidence.",
        )
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "All declared usage, support, workflow, and discrepancy signals are evaluable."
            if estimable
            else "At least one monitoring signal is not evaluable or outside the declared support domain."
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
            "Monitoring signal values and thresholds are caller-declared and issuer authority is not authenticated.",
            "Unsupported or missing evidence is never converted into a negative health finding.",
        ),
    )


def _provenance(
    request: MonitorProteinRnaTranslationHealthRequest, request_digest: str
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
        module_id=M1608_MODULE_ID,
        module_version=M1608_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.upstream_result.digest,
            request.configuration.reference_artifact.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    signals: tuple[HealthSignal, ...],
) -> tuple[TranslationHealthStatus, RollbackDecision, bool, tuple[MonitorFindingCode, ...]]:
    if any(signal.status is HealthSignalStatus.NOT_EVALUABLE for signal in signals):
        return (
            TranslationHealthStatus.ABSTAINED,
            RollbackDecision.ABSTAIN,
            True,
            (MonitorFindingCode.UPSTREAM_UNSUPPORTED, MonitorFindingCode.INPUT_INCOMPLETE),
        )
    drifting = tuple(signal for signal in signals if signal.status is HealthSignalStatus.DRIFTING)
    if not drifting:
        return TranslationHealthStatus.HEALTHY, RollbackDecision.CONTINUE, False, ()
    critical = any(
        signal.kind is HealthSignalKind.DISCREPANCY or "critical" in signal.metric.casefold()
        for signal in drifting
    )
    if critical:
        return (
            TranslationHealthStatus.CRITICAL,
            RollbackDecision.ROLLBACK,
            True,
            (MonitorFindingCode.CRITICAL_DRIFT, MonitorFindingCode.ROLLBACK_REQUIRED),
        )
    return (
        TranslationHealthStatus.DEGRADED,
        RollbackDecision.SUSPEND,
        True,
        (MonitorFindingCode.POLICY_VIOLATION,),
    )


def _report(
    request: MonitorProteinRnaTranslationHealthRequest,
    signals: tuple[HealthSignal, ...],
    evidence: tuple[EvidenceReference, ...],
    health_status: TranslationHealthStatus,
) -> TranslationHealthReport:
    assessments = tuple(
        DriftAssessment(
            assessment_id=f"assessment.{signal.signal_id}",
            signal_ids=(signal.signal_id,),
            summary=(
                "Signal is within the declared monitoring envelope."
                if signal.status is HealthSignalStatus.WITHIN_ENVELOPE
                else "Signal drift is retained for suspension or rollback review."
            ),
            status=signal.status,
            critical=signal.kind is HealthSignalKind.DISCREPANCY
            or "critical" in signal.metric.casefold(),
            evidence=evidence[:1],
        )
        for signal in signals
    )
    return TranslationHealthReport(
        report_id="report.m1608.translation-health",
        version=request.configuration.version,
        signals=signals,
        assessments=assessments,
        rollback_plan=RollbackPlan(
            plan_id="rollback.m1608.translation-health",
            trigger_conditions=(
                "Critical support or discrepancy drift is observed.",
                "Policy violation or unresolved workflow effect is observed.",
            ),
            target_version=request.configuration.version,
            action=(
                "Continue within envelope."
                if health_status is TranslationHealthStatus.HEALTHY
                else "Suspend or rollback the affected translation workflow and restore the approved version."
            ),
            recovery_steps=(
                "Quarantine the affected translation output.",
                "Verify frozen fixtures and obtain signed reviewer approval before resumption.",
            ),
            evidence=evidence[:1],
        ),
        configuration=request.configuration,
        evidence=evidence,
    )


def _diagnostics(
    signals: tuple[HealthSignal, ...],
    status: TranslationHealthStatus,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[MonitorDiagnostic, ...]:
    diagnostic_status = {
        TranslationHealthStatus.HEALTHY: MonitorDiagnosticStatus.PASS,
        TranslationHealthStatus.DEGRADED: MonitorDiagnosticStatus.WARNING,
        TranslationHealthStatus.CRITICAL: MonitorDiagnosticStatus.FAIL,
        TranslationHealthStatus.ABSTAINED: MonitorDiagnosticStatus.NOT_EVALUABLE,
    }[status]
    return tuple(
        MonitorDiagnostic(
            diagnostic_id=f"diagnostic.{signal.signal_id}",
            status=diagnostic_status,
            message=(
                "Translation signal is within envelope."
                if signal.status is HealthSignalStatus.WITHIN_ENVELOPE
                else "Translation signal requires explicit review or abstention."
            ),
            evidence=evidence[:1],
        )
        for signal in signals
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_monitoring",
            statement="Signal values, thresholds, and issuer authority are caller-declared.",
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
                statement="No translation-health state is published when monitoring support is unresolved.",
            )
        )
    return tuple(values)


class M1608TranslationMonitoringEngine:
    """Monitor typed signals and select continue, suspend, rollback, or abstain."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinRnaDiscordanceTranslationHealthResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: MonitorProteinRnaTranslationHealthRequest
    ) -> ProteinRnaDiscordanceTranslationHealthResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        signals = request.signals
        status, decision, review, findings = _classify(signals)
        report = (
            _report(request, signals, evidence, status)
            if status is not TranslationHealthStatus.ABSTAINED
            else None
        )
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_translation_health",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1608_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "health_status": status,
            "rollback_decision": decision,
            "report": report,
            "diagnostics": _diagnostics(signals, status, evidence),
            "findings": findings,
            "abstention_reason": None
            if status is not TranslationHealthStatus.ABSTAINED
            else "Translation monitoring inputs are not safely evaluable.",
            "parent_target": "protein_rna_discordance",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if not review else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1608_health_supported" if not review else "m1608_health_review",
                rationale="All monitoring signals are within the declared envelope."
                if not review
                else "Monitoring drift requires suspension or rollback review.",
            ),
            "uncertainty": _uncertainty(estimable=status is not TranslationHealthStatus.ABSTAINED),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=status is not TranslationHealthStatus.ABSTAINED),
            "human_review_required": review,
        }
        constructed = ProteinRnaDiscordanceTranslationHealthResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinRnaDiscordanceTranslationHealthResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1608ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1608ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1608ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1608ReplayVerificationError
        return validated


def monitor_protein_rna_translation_health(
    request: object,
) -> ProteinRnaDiscordanceTranslationHealthResult:
    """Public provisional M16-08 operation."""

    return M1608TranslationMonitoringEngine().infer(request)


__all__ = [
    "M1608AuthorizationError",
    "M1608ReplayVerificationError",
    "M1608TranslationMonitoringEngine",
    "monitor_protein_rna_translation_health",
    "preflight_m1608_authorization",
]
