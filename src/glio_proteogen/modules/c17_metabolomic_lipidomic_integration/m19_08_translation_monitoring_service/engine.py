"""Deterministic, replay-safe M19-08 translation monitoring engine.

The engine evaluates only caller-declared telemetry, support drift, workflow
effects, discrepancies, and a locked rollback policy. It never opens an
artifact, infers identity or consent, mutates upstream evidence, or emits a
biological, kinase, all-omics, or treatment claim.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_08 import (
    M1908_CONTRACT_VERSION,
    M1908_EVIDENCE_CLAIM,
    M1908_MODULE_ID,
    MonitorProteotypeTranslationHealthRequest,
    MonitorStatus,
    ObservationStatus,
    ProteotypeTranslationMonitoringResult,
    RollbackDecision,
    TranslationFinding,
    TranslationFindingCode,
    TranslationHealthReport,
    TranslationHealthState,
)
from glio_proteogen.contracts.m19_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorProteotypeTranslationHealthRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeTranslationMonitoringResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M1908AuthorizationError(PermissionError):
    """Caller controls do not authorize translation monitoring."""

    def __init__(self, message: str = "M19-08 requires all seven upstream controls") -> None:
        super().__init__(message)

    @classmethod
    def control(cls, role: str, expected: object, received: object) -> M1908AuthorizationError:
        return cls(f"M19-08 control {role} must be {expected}; received {received}")


class M1908ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request and digest."""

    def __init__(self, message: str = "M19-08 replay verification failed") -> None:
        super().__init__(message)

    @classmethod
    def identifier(cls) -> M1908ReplayVerificationError:
        return cls("M19-08 result identifier mismatch")

    @classmethod
    def digest(cls) -> M1908ReplayVerificationError:
        return cls("M19-08 result payload digest mismatch")

    @classmethod
    def replay(cls) -> M1908ReplayVerificationError:
        return cls("M19-08 exact replay mismatch")

    @classmethod
    def malformed(cls) -> M1908ReplayVerificationError:
        return cls("M19-08 malformed result or digest")


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1908_authorization(candidate: object) -> None:
    """Check all seven caller-declared controls before traversing observations."""

    try:
        references = _member(_member(candidate, "context"), "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _CONTROL_STATES
        }
    except Exception:  # noqa: BLE001
        raise M1908AuthorizationError from None
    for role, expected in _CONTROL_STATES.items():
        if states.get(role) != expected:
            raise M1908AuthorizationError.control(role, expected, states.get(role))


def _evidence(
    request: MonitorProteotypeTranslationHealthRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        *request.source_artifacts,
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        *(evidence.reference for item in request.telemetry for evidence in item.evidence),
        *(evidence.reference for item in request.support_drift for evidence in item.evidence),
        *(evidence.reference for item in request.workflow_effects for evidence in item.evidence),
        *(evidence.reference for item in request.discrepancies for evidence in item.evidence),
        *(evidence.reference for evidence in request.rollback_policy.evidence),
    ]
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1908_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _uncertainty(*, estimable: bool) -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        probability=None,
        rationale=(
            "Caller-declared monitoring observations are evaluable, but this module does not "
            "estimate biological truth."
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
            "observations and a locked policy.",
            "A rollback decision is an operational recovery decision, not a biological or "
            "treatment conclusion.",
        ),
    )


def _provenance(
    request: MonitorProteotypeTranslationHealthRequest,
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
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in controls
    )
    input_digests = tuple(
        dict.fromkeys(
            (
                request_digest,
                *(artifact.digest for artifact in request.source_artifacts),
                request.rollback_policy.rollback_artifact.digest,
            )
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1908_MODULE_ID,
        module_version=M1908_CONTRACT_VERSION,
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
    request: MonitorProteotypeTranslationHealthRequest,
) -> tuple[
    MonitorStatus,
    TranslationHealthState,
    RollbackDecision,
    tuple[TranslationFindingCode, ...],
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
    if any(status is ObservationStatus.NOT_EVALUABLE for status in statuses):
        return (
            MonitorStatus.ABSTAINED,
            TranslationHealthState.NOT_EVALUABLE,
            RollbackDecision.REVIEW_REQUIRED,
            (TranslationFindingCode.UPSTREAM_UNSUPPORTED,),
        )
    failures = sum(status is ObservationStatus.FAIL for status in statuses)
    warnings = sum(status is ObservationStatus.WARNING for status in statuses)
    unresolved = sum(not item.resolved for item in request.discrepancies)
    findings: list[TranslationFindingCode] = []
    if any(item.status is ObservationStatus.FAIL for item in request.telemetry):
        findings.append(TranslationFindingCode.CRITICAL_DRIFT)
    if any(item.status is ObservationStatus.FAIL for item in request.support_drift):
        findings.append(TranslationFindingCode.SUPPORT_DRIFT)
    if any(item.status is not ObservationStatus.PASS for item in request.workflow_effects):
        findings.append(TranslationFindingCode.WORKFLOW_EFFECT)
    if unresolved:
        findings.append(TranslationFindingCode.DISCREPANCY_UNRESOLVED)
    if failures + unresolved >= request.rollback_policy.critical_failure_threshold:
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
    if failures or warnings:
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
    request_digest: str,
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
            finding_id=f"finding.{request_digest.removeprefix('sha256:')}.{code.value}",
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
                "Telemetry, support drift, workflow effects, discrepancies and rollback policy "
                "are caller-declared and not independently verified."
            ),
        ),
        Limitation(
            code="rollback_is_operational",
            statement=(
                "Suspension and rollback are typed operational recovery decisions, not "
                "biological, kinase, all-omics, or treatment conclusions."
            ),
        ),
        Limitation(
            code="no_identity_or_consent_inference",
            statement=(
                "Identity, consent, provenance, support, and intended use are accepted only "
                "from their owning control authorities."
            ),
        ),
    ]
    if abstained:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported or non-evaluable inputs produce no health report.",
            )
        )
    return tuple(values)


class M1908TranslationMonitoringEngine:
    """Monitor translation health and derive a typed rollback decision."""

    __slots__ = ()

    def validate_request(
        self,
        request: object,
    ) -> MonitorProteotypeTranslationHealthRequest:
        preflight_m1908_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def infer(self, request: object) -> ProteotypeTranslationMonitoringResult:
        validated = self.validate_request(request)
        request_digest = canonical_request_digest(validated)
        evidence = _evidence(validated)
        status, health, rollback, codes = _classify(validated)
        report = (
            TranslationHealthReport(
                report_id=f"report.{request_digest.removeprefix('sha256:')}",
                version=M1908_CONTRACT_VERSION,
                telemetry=validated.telemetry,
                support_drift=validated.support_drift,
                workflow_effects=validated.workflow_effects,
                discrepancies=validated.discrepancies,
                health_state=health,
                rollback_decision=rollback,
                rollback_policy=validated.rollback_policy,
                evidence=evidence,
            )
            if status is MonitorStatus.MONITORED
            else None
        )
        abstained = report is None
        payload: dict[str, Any] = {
            "output_type": "proteotype_translation_monitoring",
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M1908_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": validated,
            "status": status,
            "health_report": report,
            "findings": _findings(request_digest, codes, evidence),
            "abstention_reason": (
                "Translation-health inputs are not safely supported." if abstained else None
            ),
            "parent_target": "proteotype",
            "emits_parent": False,
            "support_decision": (
                validated.support_decision
                if not abstained
                else SupportDecision(
                    status=SupportStatus.REVIEW_REQUIRED,
                    reason_code="m1908_monitoring_abstained",
                    rationale="Support or observation limitations prevent safe monitoring.",
                )
            ),
            "uncertainty": _uncertainty(estimable=not abstained),
            "provenance": _provenance(validated, request_digest),
            "evidence": evidence,
            "limitations": _limitations(abstained=abstained),
            "human_review_required": abstained or health is not TranslationHealthState.HEALTHY,
        }
        constructed = ProteotypeTranslationMonitoringResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeTranslationMonitoringResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.result_id != (
                f"result.{validated.request_digest.removeprefix('sha256:')}"
            ):
                raise M1908ReplayVerificationError.identifier()  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M1908ReplayVerificationError.digest()  # noqa: TRY301
            if replay:
                expected = self.infer(validated.request)
                if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                    raise M1908ReplayVerificationError.replay()  # noqa: TRY301
        except M1908ReplayVerificationError:
            raise
        except Exception as error:
            raise M1908ReplayVerificationError.malformed() from error
        return validated

    def monitor(
        self,
        request: object,
    ) -> ProteotypeTranslationMonitoringResult:
        return self.infer(request)

    def replay(
        self,
        result: object,
    ) -> ProteotypeTranslationMonitoringResult:
        return self.verify(result)


def monitor_proteotype_translation_health(
    request: object,
) -> ProteotypeTranslationMonitoringResult:
    """Public M19-08 translation-health operation."""

    return M1908TranslationMonitoringEngine().infer(request)


__all__ = [
    "M1908AuthorizationError",
    "M1908ReplayVerificationError",
    "M1908TranslationMonitoringEngine",
    "monitor_proteotype_translation_health",
    "preflight_m1908_authorization",
]
