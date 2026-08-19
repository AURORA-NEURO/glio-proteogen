"""Authorization-first deterministic translation monitoring engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_08 import (
    M1808_CONTRACT_VERSION,
    M1808_EVIDENCE_CLAIM,
    M1808_MODULE_ID,
    BiomarkerPanelTranslationMonitoringResult,
    MonitorBiomarkerPanelTranslationHealthRequest,
    MonitorStatus,
    ObservationStatus,
    RollbackDecision,
    TranslationFinding,
    TranslationFindingCode,
    TranslationHealthReport,
    TranslationHealthState,
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
from glio_proteogen.kernel.replay import revalidate_replay_result

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorBiomarkerPanelTranslationHealthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelTranslationMonitoringResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M1808AuthorizationError(PermissionError):
    """Caller controls do not authorize translation monitoring."""

    def __init__(self) -> None:
        super().__init__(
            "M18-08 requires accepted controls, resolved identity, and granted consent"
        )


class M1808ReplayVerificationError(ValueError):
    """An M18-08 result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M18-08 replay verification failed: payload digest or request mismatch")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1808_authorization(candidate: object) -> None:
    """Check seven controls before traversing observations or rollback policy."""

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
        raise M1808AuthorizationError from None
    if states != expected:
        raise M1808AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1808_authorization(candidate)
    return candidate


def _evidence(
    request: MonitorBiomarkerPanelTranslationHealthRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        request.rollback_policy.rollback_artifact,
        *(evidence.reference for item in request.telemetry for evidence in item.evidence),
        *(evidence.reference for item in request.support_drift for evidence in item.evidence),
        *(evidence.reference for item in request.workflow_effects for evidence in item.evidence),
        *(evidence.reference for item in request.discrepancies for evidence in item.evidence),
        *(evidence.reference for evidence in request.rollback_policy.evidence),
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
        EvidenceReference(reference=artifact, role="evidence", claim=M1808_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        probability=None,
        rationale=(
            "Caller-declared telemetry, support drift, workflow effects and discrepancies are "
            "evaluable."
            if estimable
            else "Unsupported monitoring inputs prevent a safe translation-health decision."
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
            "Health and rollback decisions are deterministic projections of caller-declared "
            "observations and policy.",
            "A rollback decision is not a claim about biological truth or treatment effect.",
        ),
    )


def _provenance(
    request: MonitorBiomarkerPanelTranslationHealthRequest,
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
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                request.upstream_result.digest,
                *(artifact.digest for artifact in request.source_artifacts),
                request.rollback_policy.rollback_artifact.digest,
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1808_MODULE_ID,
        module_version=M1808_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _classify(
    request: MonitorBiomarkerPanelTranslationHealthRequest,
) -> tuple[
    MonitorStatus, TranslationHealthState, RollbackDecision, tuple[TranslationFindingCode, ...]
]:
    if request.support_decision.status is not SupportStatus.SUPPORTED:
        return (
            MonitorStatus.ABSTAINED,
            TranslationHealthState.NOT_EVALUABLE,
            RollbackDecision.REVIEW_REQUIRED,
            (TranslationFindingCode.UPSTREAM_UNSUPPORTED,),
        )
    statuses = (
        *(item.status for item in request.telemetry),
        *(item.status for item in request.support_drift),
        *(item.status for item in request.workflow_effects),
    )
    critical = sum(status is ObservationStatus.FAIL for status in statuses)
    unresolved = sum(not item.resolved for item in request.discrepancies)
    not_evaluable = sum(status is ObservationStatus.NOT_EVALUABLE for status in statuses)
    warnings = sum(status is ObservationStatus.WARNING for status in statuses)
    findings: list[TranslationFindingCode] = []
    if any(item.status is ObservationStatus.FAIL for item in request.telemetry):
        findings.append(TranslationFindingCode.CRITICAL_DRIFT)
    if any(item.status is ObservationStatus.FAIL for item in request.support_drift):
        findings.append(TranslationFindingCode.SUPPORT_DRIFT)
    if any(item.status is not ObservationStatus.PASS for item in request.workflow_effects):
        findings.append(TranslationFindingCode.WORKFLOW_EFFECT)
    if unresolved:
        findings.append(TranslationFindingCode.DISCREPANCY_UNRESOLVED)
    if not_evaluable:
        return (
            MonitorStatus.ABSTAINED,
            TranslationHealthState.NOT_EVALUABLE,
            RollbackDecision.REVIEW_REQUIRED,
            tuple(findings),
        )
    if critical + unresolved >= request.rollback_policy.critical_failure_threshold:
        findings.append(TranslationFindingCode.ROLLBACK_REQUIRED)
        return (
            MonitorStatus.MONITORED,
            TranslationHealthState.ROLLBACK_REQUIRED,
            RollbackDecision.ROLLBACK,
            tuple(findings),
        )
    if unresolved:
        return (
            MonitorStatus.MONITORED,
            TranslationHealthState.SUSPENDED,
            RollbackDecision.SUSPEND,
            tuple(findings),
        )
    if critical or warnings:
        return (
            MonitorStatus.MONITORED,
            TranslationHealthState.DEGRADED,
            RollbackDecision.REVIEW_REQUIRED,
            tuple(findings),
        )
    findings.append(TranslationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW)
    return (
        MonitorStatus.MONITORED,
        TranslationHealthState.HEALTHY,
        RollbackDecision.NONE,
        tuple(findings),
    )


def _findings(
    codes: tuple[TranslationFindingCode, ...],
    evidence: tuple[EvidenceReference, ...],
) -> tuple[TranslationFinding, ...]:
    messages = {
        TranslationFindingCode.CRITICAL_DRIFT: "Critical telemetry drift was declared.",
        TranslationFindingCode.POLICY_VIOLATION: "A rollback policy violation was declared.",
        TranslationFindingCode.SUPPORT_DRIFT: "Support drift was declared.",
        TranslationFindingCode.WORKFLOW_EFFECT: "A workflow effect requires review.",
        TranslationFindingCode.DISCREPANCY_UNRESOLVED: "An unresolved discrepancy remains.",
        TranslationFindingCode.ROLLBACK_REQUIRED: "The rollback threshold was reached.",
        TranslationFindingCode.UPSTREAM_UNSUPPORTED: "Upstream support is not evaluable.",
        TranslationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW: (
            "The provisional ABI requires governed owner review."
        ),
    }
    return tuple(
        TranslationFinding(
            finding_id=f"finding.m1808.{code.value}",
            code=code,
            message=messages[code],
            evidence=evidence[:1],
        )
        for code in codes
    )


def _limitations(*, abstained: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_monitoring",
            statement=(
                "Telemetry, support drift, workflow effects, discrepancies and policy are "
                "caller-declared."
            ),
        ),
        Limitation(
            code="rollback_is_governed_decision",
            statement=(
                "Suspension and rollback are typed operational decisions, not biological or "
                "treatment conclusions."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference or consent inference is emitted."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported inputs produce no translation-health report.",
            )
        )
    return tuple(values)


class M1808TranslationMonitoringEngine:
    """Monitor translation health and derive a typed rollback decision."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelTranslationMonitoringResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: MonitorBiomarkerPanelTranslationHealthRequest,
    ) -> BiomarkerPanelTranslationMonitoringResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        status, health, rollback, codes = _classify(request)
        report = None
        if status is MonitorStatus.MONITORED:
            report = TranslationHealthReport(
                report_id=f"report.{request_hash.removeprefix('sha256:')}",
                version=M1808_CONTRACT_VERSION,
                telemetry=request.telemetry,
                support_drift=request.support_drift,
                workflow_effects=request.workflow_effects,
                discrepancies=request.discrepancies,
                health_state=health,
                rollback_decision=rollback,
                rollback_policy=request.rollback_policy,
                evidence=evidence,
            )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1808_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "health_report": report,
            "findings": _findings(codes, evidence),
            "abstention_reason": None
            if report is not None
            else "Translation-health inputs are not safely supported.",
            "parent_target": "biomarker panel",
            "emits_parent": False,
            "support_decision": (
                request.support_decision
                if report is not None
                else SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="m1808_monitoring_abstained",
                    rationale="Support limitations prevent safe translation monitoring.",
                )
            ),
            "uncertainty": _uncertainty(estimable=report is not None),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(abstained=report is None),
            "human_review_required": report is None or health is not TranslationHealthState.HEALTHY,
        }
        constructed = BiomarkerPanelTranslationMonitoringResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelTranslationMonitoringResult:
        try:
            validated = revalidate_replay_result(_RESULT_ADAPTER, result)
        except Exception as error:
            raise M1808ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1808ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1808ReplayVerificationError
        return validated

    def adapt(
        self,
        request: object,
    ) -> BiomarkerPanelTranslationMonitoringResult:
        """Compatibility-named execution seam used by evaluator harnesses."""

        return self.infer(request)

    def replay(
        self,
        result: object,
    ) -> BiomarkerPanelTranslationMonitoringResult:
        """Compatibility-named exact replay verifier."""

        return self.verify(result)


def monitor_biomarker_panel_translation_health(
    request: object,
) -> BiomarkerPanelTranslationMonitoringResult:
    """Public provisional M18-08 monitoring operation."""

    return M1808TranslationMonitoringEngine().infer(request)


__all__ = [
    "M1808AuthorizationError",
    "M1808ReplayVerificationError",
    "M1808TranslationMonitoringEngine",
    "monitor_biomarker_panel_translation_health",
    "preflight_m1808_authorization",
]
