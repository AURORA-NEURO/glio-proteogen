"""Authorization-first deterministic M20-08 monitoring engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_08 import (
    M2008_CONTRACT_VERSION,
    M2008_MODULE_ID,
    DriftAssessment,
    HealthSignal,
    HealthSignalKind,
    HealthSignalStatus,
    MonitorDiagnostic,
    MonitorDiagnosticStatus,
    MonitorFindingCode,
    MonitorProteinSubtypeTranslationHealthRequest,
    ProteinSubtypeTranslationHealthResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeTranslationHealthResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EVIDENCE_CLAIM: Final = "Caller-declared M20-08 translation-health and rollback evidence."


class M2008AuthorizationError(PermissionError):
    """Caller controls do not authorize translation monitoring."""

    def __init__(self) -> None:
        super().__init__(
            "M20-08 requires accepted controls, resolved identity, and granted consent"
        )


class M2008ReplayVerificationError(ValueError):
    """An M20-08 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M20-08 replay verification failed: payload or request mismatch")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m2008_authorization(candidate: object) -> None:
    """Check all seven controls before traversing monitoring inputs."""

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
        raise M2008AuthorizationError from None
    if states != expected:
        raise M2008AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m2008_authorization(candidate)
    return candidate


def _evidence(
    request: MonitorProteinSubtypeTranslationHealthRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        request.configuration.reference_artifact,
        *request.source_artifacts,
        *(item.reference for item in request.configuration.evidence),
        *(artifact for signal in request.signals for artifact in signal.source_artifacts),
        *(item.reference for signal in request.signals for item in signal.evidence),
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
        EvidenceReference(reference=artifact, role="evidence", claim=_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if estimable else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if estimable else None,
        rationale=(
            "All caller-declared monitoring signals are evaluable against the locked policy."
            if estimable
            else "At least one monitoring signal is not evaluable; the engine abstains safely."
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
            "Signal values, envelopes, and issuer authority are caller-declared.",
            "Rollback is an operational control decision, not a biological or treatment claim.",
        ),
    )


def _provenance(
    request: MonitorProteinSubtypeTranslationHealthRequest,
    request_digest: str,
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
        module_id=M2008_MODULE_ID,
        module_version=M2008_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_digest,
                    request.upstream_result.digest,
                    request.configuration.reference_artifact.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
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
) -> tuple[TranslationHealthStatus, RollbackDecision, tuple[MonitorFindingCode, ...]]:
    if any(signal.status is HealthSignalStatus.NOT_EVALUABLE for signal in signals):
        return (
            TranslationHealthStatus.ABSTAINED,
            RollbackDecision.ABSTAIN,
            (MonitorFindingCode.UPSTREAM_UNSUPPORTED, MonitorFindingCode.INPUT_INCOMPLETE),
        )
    drifting = tuple(signal for signal in signals if signal.status is HealthSignalStatus.DRIFTING)
    if not drifting:
        return (
            TranslationHealthStatus.HEALTHY,
            RollbackDecision.CONTINUE,
            (MonitorFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,),
        )
    critical = any(
        signal.kind is HealthSignalKind.DISCREPANCY or "critical" in signal.metric.casefold()
        for signal in drifting
    )
    if critical:
        return (
            TranslationHealthStatus.CRITICAL,
            RollbackDecision.ROLLBACK,
            (MonitorFindingCode.CRITICAL_DRIFT, MonitorFindingCode.ROLLBACK_REQUIRED),
        )
    return (
        TranslationHealthStatus.DEGRADED,
        RollbackDecision.SUSPEND,
        (MonitorFindingCode.POLICY_VIOLATION,),
    )


def _report(
    request: MonitorProteinSubtypeTranslationHealthRequest,
    request_digest: str,
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
        for signal in request.signals
    )
    action = (
        "Continue within the locked monitoring envelope."
        if health_status is TranslationHealthStatus.HEALTHY
        else (
            "Suspend or rollback the affected translation workflow and restore the approved "
            "version."
        )
    )
    return TranslationHealthReport(
        report_id=f"report.{request_digest.removeprefix('sha256:')}",
        version=request.configuration.version,
        signals=request.signals,
        assessments=assessments,
        rollback_plan=RollbackPlan(
            plan_id=f"rollback.{request_digest.removeprefix('sha256:')}",
            trigger_conditions=(
                "Critical support or discrepancy drift is observed.",
                "A locked monitoring policy threshold requires review.",
            ),
            target_version=request.configuration.version,
            action=action,
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


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_monitoring",
            statement="Signal values, thresholds, and issuer authority are caller-declared.",
        ),
        Limitation(
            code="rollback_is_operational",
            statement=(
                "Suspension and rollback are typed operational decisions, not biological or "
                "treatment conclusions."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, all-omics fusion, treatment recommendation, identity "
                "inference, or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Unsupported or non-evaluable monitoring inputs produce no health report."
                ),
            )
        )
    return tuple(values)


class M2008TranslationMonitoringEngine:
    """Monitor typed signals and select continue, suspend, rollback, or abstain."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeTranslationHealthResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: MonitorProteinSubtypeTranslationHealthRequest
    ) -> ProteinSubtypeTranslationHealthResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, decision, findings = _classify(request.signals)
        report = (
            _report(request, request_hash, evidence, status)
            if status is not TranslationHealthStatus.ABSTAINED
            else None
        )
        review = status is not TranslationHealthStatus.HEALTHY
        payload: dict[str, object] = {
            "output_type": "protein_subtype_translation_health",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M2008_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "health_status": status,
            "rollback_decision": decision,
            "report": report,
            "diagnostics": _diagnostics(request.signals, status, evidence),
            "findings": findings,
            "abstention_reason": (
                None
                if report is not None
                else "Translation monitoring inputs are not safely evaluable."
            ),
            "parent_target": "protein subtype",
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if not review else SupportStatus.REVIEW_REQUIRED,
                reason_code="m2008_health_supported" if not review else "m2008_health_review",
                rationale=(
                    "All monitoring signals are within the locked envelope."
                    if not review
                    else "Monitoring drift or non-evaluable input requires explicit review."
                ),
            ),
            "uncertainty": _uncertainty(estimable=not review),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=status is TranslationHealthStatus.ABSTAINED),
            "human_review_required": review,
        }
        constructed = ProteinSubtypeTranslationHealthResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinSubtypeTranslationHealthResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M2008ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M2008ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2008ReplayVerificationError
        return validated

    def replay(self, result: object) -> ProteinSubtypeTranslationHealthResult:
        """Compatibility-named exact replay verifier."""

        return self.verify(result)


def monitor_protein_subtype_translation_health(
    request: object,
) -> ProteinSubtypeTranslationHealthResult:
    """Public provisional M20-08 monitoring operation."""

    return M2008TranslationMonitoringEngine().infer(request)


__all__ = [
    "M2008AuthorizationError",
    "M2008ReplayVerificationError",
    "M2008TranslationMonitoringEngine",
    "monitor_protein_subtype_translation_health",
    "preflight_m2008_authorization",
]
