"""Replay-safe translation health monitoring and rollback decisions for M17-08."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_08 import (
    M1708_EVIDENCE_CLAIM,
    M1708_MODULE_ID,
    MonitorStatus,
    MonitorVariantPeptideTranslationHealthRequest,
    ObservationStatus,
    RollbackDecision,
    TranslationFinding,
    TranslationFindingCode,
    TranslationHealthReport,
    TranslationHealthState,
    VariantPeptideTranslationMonitoringResult,
)
from glio_proteogen.contracts.m17_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorVariantPeptideTranslationHealthRequest)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_CONTROL_STATES: Final = {
    "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
    "identity_lineage": IdentityLineageState.RESOLVED.value,
    "provenance": UpstreamDecisionState.ACCEPTED.value,
    "consent": ConsentState.GRANTED.value,
    "quality": UpstreamDecisionState.ACCEPTED.value,
    "support": UpstreamDecisionState.ACCEPTED.value,
    "intended_use": UpstreamDecisionState.ACCEPTED.value,
}


class M1708AuthorizationError(ValueError):
    """Raised before health observations are evaluated when controls are unsafe."""


class M1708ReplayError(ValueError):
    """Raised when a result digest no longer binds to its request or payload."""


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def preflight_m1708_authorization(candidate: object) -> None:
    """Require all seven caller-declared controls before monitoring."""

    references = _member(_member(candidate, "context"), "references")
    if references is None:
        raise M1708AuthorizationError("M17-08 requires all seven upstream controls")  # noqa: TRY003
    for name, expected in _CONTROL_STATES.items():
        decision = _member(references, name)
        actual = _member(decision, "state")
        actual_value = getattr(actual, "value", actual)
        if actual_value != expected:
            raise M1708AuthorizationError(  # noqa: TRY003
                f"M17-08 control {name} must be {expected}; received {actual_value}"
            )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M17-08 monitors declared health evidence; it does not estimate biology.",
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
            "Health state is sensitive to declared baseline, allowed delta, support drift, "
            "workflow effects, discrepancy resolution and rollback threshold.",
        ),
    )


def _control_decisions(
    request: MonitorVariantPeptideTranslationHealthRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records: list[ControlDecisionRecord] = []
    for role, decision in (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    ):
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=decision.state.value,
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
            )
        )
    records.extend(
        (
            ControlDecisionRecord(
                role=ControlRole.IDENTITY_LINEAGE,
                decision_id=refs.identity_lineage.decision_id,
                state=refs.identity_lineage.state.value,
                policy_version=refs.identity_lineage.policy_version,
                evidence_digest=refs.identity_lineage.evidence.digest,
                subject_digest=refs.identity_lineage.binding_digest,
            ),
            ControlDecisionRecord(
                role=ControlRole.CONSENT,
                decision_id=refs.consent.decision_id,
                state=refs.consent.state.value,
                policy_version=refs.consent.policy_version,
                evidence_digest=refs.consent.evidence.digest,
            ),
        )
    )
    return tuple(records)


def _provenance(request: MonitorVariantPeptideTranslationHealthRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1708_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.rollback_policy),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(
    request: MonitorVariantPeptideTranslationHealthRequest,
) -> tuple[EvidenceReference, ...]:
    items: list[EvidenceReference] = [
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M1708_EVIDENCE_CLAIM,
        )
        for artifact in request.source_artifacts
    ]
    items.extend(request.rollback_policy.evidence)
    for telemetry_observation in request.telemetry:
        items.extend(telemetry_observation.evidence)
    for support_observation in request.support_drift:
        items.extend(support_observation.evidence)
    for workflow_observation in request.workflow_effects:
        items.extend(workflow_observation.evidence)
    for discrepancy_observation in request.discrepancies:
        items.extend(discrepancy_observation.evidence)
    return tuple(items)


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="translation_health_policy_only",
            statement=(
                "This module monitors declared translation-health evidence and does not "
                "infer biology."
            ),
        ),
        Limitation(
            code="upstream_not_authenticated",
            statement="The upstream M17-07 artifact and issuer authority are not authenticated.",
        ),
        Limitation(
            code="no_kinase_or_treatment_claim",
            statement=(
                "Kinase ownership, all-omics fusion, treatment, identity and consent inference "
                "remain outside this module."
            ),
        ),
    )


def _health_plan(  # noqa: C901, PLR0912
    request: MonitorVariantPeptideTranslationHealthRequest,
) -> tuple[TranslationHealthState, RollbackDecision, tuple[TranslationFinding, ...]]:
    findings: list[TranslationFinding] = []
    critical_count = 0
    warning_count = 0
    not_evaluable = False
    for telemetry_observation in request.telemetry:
        if telemetry_observation.status is ObservationStatus.FAIL:
            critical_count += 1
            findings.append(
                TranslationFinding(
                    finding_id=f"finding.{telemetry_observation.observation_id}",
                    code=TranslationFindingCode.CRITICAL_DRIFT,
                    message=(
                        f"Telemetry metric {telemetry_observation.metric_name} exceeded "
                        "its declared health envelope."
                    ),
                    evidence=telemetry_observation.evidence,
                )
            )
        elif telemetry_observation.status is ObservationStatus.WARNING:
            warning_count += 1
        elif telemetry_observation.status is ObservationStatus.NOT_EVALUABLE:
            not_evaluable = True
    for support_observation in request.support_drift:
        if support_observation.status is ObservationStatus.FAIL:
            critical_count += 1
            findings.append(
                TranslationFinding(
                    finding_id=f"finding.{support_observation.observation_id}",
                    code=TranslationFindingCode.SUPPORT_DRIFT,
                    message=(
                        f"Support dimension {support_observation.support_dimension} drifted "
                        "outside the declared envelope."
                    ),
                    evidence=support_observation.evidence,
                )
            )
        elif support_observation.status is ObservationStatus.WARNING:
            warning_count += 1
        elif support_observation.status is ObservationStatus.NOT_EVALUABLE:
            not_evaluable = True
    for workflow_observation in request.workflow_effects:
        if workflow_observation.status is ObservationStatus.FAIL:
            critical_count += 1
            findings.append(
                TranslationFinding(
                    finding_id=f"finding.{workflow_observation.observation_id}",
                    code=TranslationFindingCode.WORKFLOW_EFFECT,
                    message=(
                        f"Workflow {workflow_observation.workflow} produced a declared "
                        "critical effect."
                    ),
                    evidence=workflow_observation.evidence,
                )
            )
        elif workflow_observation.status is ObservationStatus.WARNING:
            warning_count += 1
        elif workflow_observation.status is ObservationStatus.NOT_EVALUABLE:
            not_evaluable = True
    for discrepancy_observation in request.discrepancies:
        if not discrepancy_observation.resolved:
            findings.append(
                TranslationFinding(
                    finding_id=f"finding.{discrepancy_observation.discrepancy_id}",
                    code=TranslationFindingCode.DISCREPANCY_UNRESOLVED,
                    message="A declared discrepancy remains unresolved and requires review.",
                    evidence=discrepancy_observation.evidence,
                )
            )
        if discrepancy_observation.status is ObservationStatus.NOT_EVALUABLE:
            not_evaluable = True
        elif (
            discrepancy_observation.status is ObservationStatus.FAIL
            and discrepancy_observation.resolved
        ):
            critical_count += 1
    if not_evaluable:
        findings.append(
            TranslationFinding(
                finding_id=f"finding.{request.request_id}.not-evaluable",
                code=TranslationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="At least one health observation is not evaluable; the module abstains.",
            )
        )
        return (
            TranslationHealthState.NOT_EVALUABLE,
            RollbackDecision.REVIEW_REQUIRED,
            tuple(findings),
        )
    if critical_count >= request.rollback_policy.critical_failure_threshold:
        findings.append(
            TranslationFinding(
                finding_id=f"finding.{request.request_id}.rollback",
                code=TranslationFindingCode.ROLLBACK_REQUIRED,
                message="Critical drift reached the declared rollback threshold.",
                evidence=request.rollback_policy.evidence,
            )
        )
        return (
            TranslationHealthState.ROLLBACK_REQUIRED,
            RollbackDecision.ROLLBACK,
            tuple(findings),
        )
    if any(item.code is TranslationFindingCode.DISCREPANCY_UNRESOLVED for item in findings):
        return TranslationHealthState.SUSPENDED, RollbackDecision.SUSPEND, tuple(findings)
    if warning_count:
        return TranslationHealthState.DEGRADED, RollbackDecision.REVIEW_REQUIRED, tuple(findings)
    return TranslationHealthState.HEALTHY, RollbackDecision.NONE, tuple(findings)


class M1708Engine:
    """Monitor caller-declared translation health without traversing upstream content."""

    def validate_request(self, candidate: object) -> MonitorVariantPeptideTranslationHealthRequest:
        preflight_m1708_authorization(candidate)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def adapt(self, candidate: object) -> VariantPeptideTranslationMonitoringResult:
        request = self.validate_request(candidate)
        request_digest = canonical_request_digest(request)
        state, decision, findings = _health_plan(request)
        evidence = _evidence(request)
        if state is TranslationHealthState.NOT_EVALUABLE:
            status = MonitorStatus.ABSTAINED
            report = None
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="translation_health_not_evaluable",
                rationale=(
                    "No health state is emitted when a required observation is not evaluable."
                ),
            )
            abstention_reason = (
                "Translation-health monitoring abstained on a not-evaluable observation."
            )
        else:
            status = MonitorStatus.MONITORED
            report = TranslationHealthReport(
                report_id=f"report.{request.request_id}",
                version=request.rollback_policy.version,
                telemetry=request.telemetry,
                support_drift=request.support_drift,
                workflow_effects=request.workflow_effects,
                discrepancies=request.discrepancies,
                health_state=state,
                rollback_decision=decision,
                rollback_policy=request.rollback_policy,
                evidence=evidence,
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code=f"translation_health_{state.value}",
                rationale=(
                    "Declared telemetry and support evidence produced a bounded health state."
                ),
            )
            abstention_reason = None
        payload: dict[str, Any] = {
            "output_type": "variant_peptide_translation_monitoring",
            "result_id": f"result.{request.request_id}",
            "result_version": "0.1.0-provisional",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "health_report": report,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": "variant peptide",
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": bool(findings) or state is not TranslationHealthState.HEALTHY,
        }
        payload["result_digest"] = result_payload_digest(
            VariantPeptideTranslationMonitoringResult.model_construct(**payload)
        )
        return VariantPeptideTranslationMonitoringResult.model_validate(payload, strict=True)

    def replay(
        self,
        result: VariantPeptideTranslationMonitoringResult,
    ) -> VariantPeptideTranslationMonitoringResult:
        if result.request_digest != canonical_request_digest(result.request):
            raise M1708ReplayError("M17-08 result request digest mismatch")  # noqa: TRY003
        if result.result_digest != result_payload_digest(result):
            raise M1708ReplayError("M17-08 result payload digest mismatch")  # noqa: TRY003
        return result


def monitor_variant_peptide_translation_health(
    candidate: object,
) -> VariantPeptideTranslationMonitoringResult:
    return M1708Engine().adapt(candidate)


__all__ = [
    "M1708AuthorizationError",
    "M1708Engine",
    "M1708ReplayError",
    "monitor_variant_peptide_translation_health",
    "preflight_m1708_authorization",
]
