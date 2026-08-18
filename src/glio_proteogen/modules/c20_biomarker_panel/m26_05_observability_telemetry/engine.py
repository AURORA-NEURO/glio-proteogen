"""Deterministic, caller-declared M26-05 observability runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_05 import (
    M2605_CONTRACT_VERSION,
    M2605_MODULE_ID,
    AlertRecord,
    AlertSeverity,
    AlertState,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    SafeFailureReport,
    TelemetryFinding,
    TelemetryFindingCode,
    TelemetryStatus,
    TelemetryStream,
)
from glio_proteogen.contracts.m26_05.canonical import (
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
    ExecutionContext,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final[TypeAdapter[EmitProteomicsTelemetryRequest]] = TypeAdapter(
    EmitProteomicsTelemetryRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteomicsTelemetryResult]] = TypeAdapter(
    ProteomicsTelemetryResult
)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_EXPECTED_CONTROL_STATES: Final[dict[ControlRole, str]] = {
    ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
    ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.CONSENT: ConsentState.GRANTED.value,
    ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
    ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
}
_LIMITATIONS: Final = (
    Limitation(
        code="telemetry_traceability_only",
        statement=(
            "This module records caller-declared observability signals and operational alerts; "
            "it does not infer protein subtype, treatment, identity, consent, or kinase state."
        ),
    ),
    Limitation(
        code="upstream_media_boundary",
        statement=(
            "The M26-04 gateway artifact is accepted by declared media type only; issuer "
            "authority and gateway semantics are not authenticated here."
        ),
    ),
    Limitation(
        code="research_use_only",
        statement=(
            "This provisional telemetry service is for research and operational review until "
            "owner, transport, retention, and prospective validation are complete."
        ),
    ),
)
_DRIFT_REVIEW_THRESHOLD: Final = 0.5
_ERROR_REVIEW_THRESHOLD: Final = 0.05


class M2605AuthorizationError(ValueError):
    """Caller-declared controls do not authorize telemetry material traversal."""

    def __init__(self) -> None:
        super().__init__(
            "M26-05 telemetry requires accepted configuration, resolved identity, granted "
            "consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2605ReplayError(ValueError):
    """A telemetry result failed canonical replay verification."""

    def __init__(self) -> None:
        super().__init__("M26-05 telemetry replay verification failed")


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _state(candidate: object) -> object:
    value = _member(candidate, "state")
    return getattr(value, "value", value)


def preflight_m2605_authorization(candidate: object) -> None:
    """Fail closed on all seven controls before reading telemetry samples."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        authorized = all(
            _state(_member(references, role.value)) == expected
            for role, expected in _EXPECTED_CONTROL_STATES.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2605AuthorizationError from None
    if not authorized:
        raise M2605AuthorizationError


def _evidence(request: EmitProteomicsTelemetryRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared M26-05 observability evidence; issuer authority "
                "is not authenticated."
            ),
        )
        for artifact in request.source_artifacts
    )


def _findings(request: EmitProteomicsTelemetryRequest) -> tuple[TelemetryFinding, ...]:
    evidence = _evidence(request)
    observed = {sample.metric for sample in request.samples}
    findings: list[TelemetryFinding] = []
    for metric in request.requested_metrics:
        if metric not in observed:
            findings.append(  # noqa: PERF401 - preserve stable requested-metric order.
                TelemetryFinding(
                    finding_id=f"finding.m2605.missing.{metric.value}",
                    code=TelemetryFindingCode.CRITICAL_SIGNAL_MISSING,
                    message=f"requested telemetry metric {metric.value} is missing",
                    evidence=evidence,
                )
            )
    for sample in request.samples:
        if sample.metric.value == "drift" and sample.value >= _DRIFT_REVIEW_THRESHOLD:
            findings.append(
                TelemetryFinding(
                    finding_id=f"finding.m2605.drift.{sample.sample_id}",
                    code=TelemetryFindingCode.DRIFT_DETECTED,
                    message=f"drift signal {sample.sample_id} meets the review threshold",
                    evidence=evidence,
                )
            )
        if sample.metric.value == "errors" and sample.value >= _ERROR_REVIEW_THRESHOLD:
            findings.append(
                TelemetryFinding(
                    finding_id=f"finding.m2605.errors.{sample.sample_id}",
                    code=TelemetryFindingCode.ERROR_BUDGET_EXCEEDED,
                    message=f"error signal {sample.sample_id} meets the review threshold",
                    evidence=evidence,
                )
            )
    if not findings:
        findings.append(
            TelemetryFinding(
                finding_id="finding.m2605.provisional-review",
                code=TelemetryFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Provisional telemetry ABI and retention semantics require owner review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _alert(
    request: EmitProteomicsTelemetryRequest, findings: tuple[TelemetryFinding, ...]
) -> AlertRecord:
    evidence = _evidence(request)
    trigger = max(sample.observed_at for sample in request.samples)
    severe = any(item.code is TelemetryFindingCode.ERROR_BUDGET_EXCEEDED for item in findings)
    drift = any(item.code is TelemetryFindingCode.DRIFT_DETECTED for item in findings)
    if severe or drift:
        return AlertRecord(
            alert_id="alert.m2605.operational-review",
            state=AlertState.OPEN,
            severity=AlertSeverity.ERROR if severe else AlertSeverity.WARNING,
            metric=(
                next(
                    sample.metric
                    for sample in request.samples
                    if sample.metric.value == ("errors" if severe else "drift")
                )
            ),
            message="Telemetry threshold requires operational review.",
            triggered_at=trigger,
            evidence=evidence,
        )
    return AlertRecord(
        alert_id="alert.m2605.clear",
        state=AlertState.CLEAR,
        severity=AlertSeverity.INFO,
        metric=request.requested_metrics[0],
        message="No operational alert threshold was crossed.",
        evidence=evidence,
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M26-05 does not estimate {dimension} uncertainty from telemetry.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "Telemetry alerts are operational signals and are not biological findings.",
            "Missing or unsupported signals abstain and never become negative evidence.",
        ),
    )


def _controls(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=getattr(reference.state, "value", reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(
    request: EmitProteomicsTelemetryRequest,
    request_digest: str,
    controls: tuple[ControlDecisionRecord, ...],
) -> ProvenanceRecord:
    references = request.context.references
    configuration_digest = sha256_digest(
        {
            "module": M2605_MODULE_ID,
            "contract": M2605_CONTRACT_VERSION,
            "operation": request.operation,
            "upstream": request.upstream_result.media_type,
            "metrics": tuple(item.value for item in request.requested_metrics),
        }
    )
    return ProvenanceRecord(
        activity_id=f"activity.m2605.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M2605_MODULE_ID,
        module_version=M2605_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    request_digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                    *(item.evidence_digest for item in controls),
                }
            )
        ),
        configuration_digest=configuration_digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _safe_failure(
    request: EmitProteomicsTelemetryRequest,
    findings: tuple[TelemetryFinding, ...],
) -> SafeFailureReport:
    return SafeFailureReport(
        report_id="safe-failure.m2605.telemetry",
        version=M2605_CONTRACT_VERSION,
        trigger=", ".join(sorted({item.code.value for item in findings})),
        action="Do not publish telemetry as an operationally supported stream; review inputs.",
        recovery_note="Supply every requested finite metric with retained evidence and rerun.",
        evidence=_evidence(request),
    )


def _build_result(request: EmitProteomicsTelemetryRequest) -> ProteomicsTelemetryResult:
    request_digest = canonical_request_digest(request)
    findings = _findings(request)
    critical = any(item.code is TelemetryFindingCode.CRITICAL_SIGNAL_MISSING for item in findings)
    status = TelemetryStatus.ABSTAINED if critical else TelemetryStatus.EMITTED
    controls = _controls(request.context)
    evidence = _evidence(request)
    provenance = _provenance(request, request_digest, controls)
    stream = (
        TelemetryStream(
            stream_id=f"stream.m2605.{request_digest.removeprefix('sha256:')}",
            version=M2605_CONTRACT_VERSION,
            samples=request.samples,
            reviewer_actions=request.reviewer_actions,
            findings=findings,
            evidence=evidence,
        )
        if status is TelemetryStatus.EMITTED
        else None
    )
    candidate: dict[str, Any] = {
        "output_type": "proteomics_observability_telemetry",
        "result_id": f"result.m2605.{request_digest.removeprefix('sha256:')}",
        "result_version": M2605_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "telemetry_stream": stream,
        "dashboards": request.dashboard_definitions if stream is not None else (),
        "alert": _alert(request, findings) if stream is not None else None,
        "findings": findings,
        "safe_failure_report": _safe_failure(request, findings) if stream is None else None,
        "abstention_reason": None
        if stream is not None
        else "Telemetry emission abstained because required operational signals are missing.",
        "parent_target": "protein subtype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED if stream is not None else SupportStatus.REVIEW_REQUIRED,
            reason_code="telemetry_supported" if stream is not None else "telemetry_abstained",
            rationale=(
                "All requested finite telemetry signals are retained with evidence."
                if stream is not None
                else (
                    "Required telemetry signals are missing; no negative biological "
                    "inference is made."
                )
            ),
        ),
        "uncertainty": _uncertainty(),
        "provenance": provenance,
        "evidence": evidence,
        "limitations": _LIMITATIONS,
        "human_review_required": stream is None
        or any(
            item.code
            in {TelemetryFindingCode.DRIFT_DETECTED, TelemetryFindingCode.ERROR_BUDGET_EXCEEDED}
            for item in findings
        ),
    }
    materialized = ProteomicsTelemetryResult.model_construct(**candidate)
    payload = materialized.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(materialized)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M2605ObservabilityEngine:
    """Build one deterministic telemetry result without I/O or learned inference."""

    __slots__ = ()

    def emit(self, request: EmitProteomicsTelemetryRequest) -> ProteomicsTelemetryResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m2605_authorization(validated)
        return _build_result(validated)


def emit_proteomics_telemetry(request: object) -> ProteomicsTelemetryResult:
    """Public stateless M26-05 entry point."""

    return M2605ObservabilityEngine().emit(_REQUEST_ADAPTER.validate_python(request, strict=True))


def verify_telemetry_result(result: ProteomicsTelemetryResult) -> ProteomicsTelemetryResult:
    """Recompute and compare the complete result bound to its request.

    A valid result digest proves only that the supplied payload is internally
    self-consistent. A caller who forges a nested telemetry value can also
    recompute that digest, so replay must use the embedded request as its
    source of truth and compare every deterministic output field.
    """

    try:
        validated = _RESULT_ADAPTER.validate_python(result, strict=True)
    except ValidationError as error:
        raise M2605ReplayError from error
    if validated.request_digest != canonical_request_digest(validated.request):
        raise M2605ReplayError
    if validated.result_digest != result_payload_digest(validated):
        raise M2605ReplayError
    if validated.status is TelemetryStatus.EMITTED and validated.telemetry_stream is None:
        raise M2605ReplayError
    try:
        expected = M2605ObservabilityEngine().emit(validated.request)
    except Exception as error:
        raise M2605ReplayError from error
    if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
        raise M2605ReplayError from None
    return validated


__all__ = [
    "M2605AuthorizationError",
    "M2605ObservabilityEngine",
    "M2605ReplayError",
    "emit_proteomics_telemetry",
    "preflight_m2605_authorization",
    "verify_telemetry_result",
]
