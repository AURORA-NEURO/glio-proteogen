"""Deterministic, caller-declared M27-05 observability runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_05 import (
    M2705_CONTRACT_VERSION,
    M2705_M2704_INPUT_MEDIA_TYPE,
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MODULE_ID,
    M2705_PARENT,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    SafeFailureReport,
    TelemetryStatus,
)
from glio_proteogen.contracts.m27_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(EmitProteomicsTelemetryRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteomicsTelemetryResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64


class M2705AuthorizationError(ValueError):
    """The caller-declared controls do not authorize telemetry emission."""

    def __init__(self) -> None:
        super().__init__(
            "M27-05 telemetry requires accepted configuration, resolved identity, granted "
            "consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2705ReplayError(ValueError):
    """A telemetry result failed deterministic replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    state = _member(candidate, "state")
    return getattr(state, "value", state)


def preflight_m2705_authorization(candidate: object) -> None:
    """Check all seven controls before traversing telemetry inputs."""

    try:
        request_id = _member(candidate, "request_id")
        context = _member(candidate, "context")
        context_identity_matches = request_id == _member(context, "request_id")
        references = _member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        authorized = all(
            _state_value(_member(references, role)) == state for role, state in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2705AuthorizationError from None
    if not context_identity_matches or not authorized:
        raise M2705AuthorizationError


def _validate_request(candidate: object) -> EmitProteomicsTelemetryRequest:
    if isinstance(candidate, (bytes, bytearray, str)):
        decoded = strict_json_loads(candidate, max_bytes=M2705_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(candidate)), strict=True)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _evidence(request: EmitProteomicsTelemetryRequest) -> tuple[EvidenceReference, ...]:
    artifacts = (request.upstream_result, *request.source_artifacts)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M27-05 observability source artifact.",
        )
        for artifact in unique.values()
    )


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M27-05 does not estimate {dimension} uncertainty from telemetry metadata.",
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
            "Telemetry preserves caller-declared operational signals and does not estimate "
            "complex-activity biology or clinical uncertainty.",
        ),
    )


def _provenance(request: EmitProteomicsTelemetryRequest, request_digest: str) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(_state_value(decision)),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id="m2705.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2705_MODULE_ID,
        module_version=M2705_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request.upstream_result.digest,
                    *(artifact.digest for artifact in request.source_artifacts),
                )
            )
        ),
        configuration_digest=sha256_digest(
            {
                "module": M2705_MODULE_ID,
                "contract": M2705_CONTRACT_VERSION,
                "requested_metrics": request.requested_metrics,
                "dashboard_definitions": request.dashboard_definitions,
            }
        ),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


class M2705TelemetryEngine:
    """Emit one deterministic observability stream or an explicit safe failure."""

    __slots__ = ()

    def emit(self, request: object) -> ProteomicsTelemetryResult:
        preflight_m2705_authorization(request)
        canonical = _validate_request(request)
        request_digest = canonical_request_digest(canonical)
        evidence = _evidence(canonical)
        blocking = canonical.upstream_result.media_type != M2705_M2704_INPUT_MEDIA_TYPE
        status = TelemetryStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.UNSUPPORTED if blocking else SupportStatus.REVIEW_REQUIRED,
            reason_code=(
                "upstream_media_type_unsupported" if blocking else "telemetry_observations_missing"
            ),
            rationale=(
                "The caller-declared upstream is not the reviewed M27-04 gateway media type."
                if blocking
                else (
                    "The request declares metric kinds and evidence only; no observed "
                    "telemetry values are bound."
                )
            ),
        )
        stream = None
        dashboards: tuple[DashboardDefinition, ...] = ()
        alert = None
        trigger = (
            "upstream_media_type_unsupported" if blocking else "telemetry_observations_missing"
        )
        failure = SafeFailureReport(
            report_id="m2705.safe-failure." + request_digest.removeprefix("sha256:"),
            version=M2705_CONTRACT_VERSION,
            trigger=trigger,
            action=(
                "abstain_without_telemetry_traversal"
                if blocking
                else "abstain_without_fabricating_telemetry"
            ),
            recovery_note=(
                "Supply a reviewed M27-04 gateway artifact reference and rerun."
                if blocking
                else "Supply bounded observed values with a confirmed M27-05 ABI and rerun."
            ),
            evidence=evidence,
        )
        reason = (
            "upstream M27-04 media type is unsupported"
            if blocking
            else "M27-05 telemetry observations are not present in the request"
        )
        payload: dict[str, Any] = {
            "result_id": "m2705.result." + request_digest.removeprefix("sha256:"),
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "request_digest": request_digest,
            "status": status,
            "telemetry_stream": stream,
            "dashboards": dashboards,
            "alert": alert,
            "safe_failure_report": failure,
            "abstention_reason": reason,
            "parent_target": M2705_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(
                    code="operational_metadata_only",
                    statement=(
                        "Telemetry does not infer proteins, proteoforms, isoforms, or "
                        "glioma biology."
                    ),
                ),
                Limitation(
                    code="caller_declared_signals",
                    statement=(
                        "Signals are caller-declared and are not independently measured "
                        "or calibrated."
                    ),
                ),
            ),
            "human_review_required": True,
        }
        provisional = ProteomicsTelemetryResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: object) -> ProteomicsTelemetryResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2705ReplayError  # noqa: TRY301
            expected_id = "m2705.result." + validated.request_digest.removeprefix("sha256:")
            if validated.result_id != expected_id:
                raise M2705ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2705ReplayError  # noqa: TRY301
            expected = self.emit(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2705ReplayError  # noqa: TRY301
        except M2705ReplayError:
            raise
        except Exception as error:
            raise M2705ReplayError from error
        return validated


def emit_search_quant_observability_telemetry(
    request: object,
) -> ProteomicsTelemetryResult:
    """Public stateless M27-05 telemetry operation."""

    return M2705TelemetryEngine().emit(request)


__all__ = [
    "M2705AuthorizationError",
    "M2705ReplayError",
    "M2705TelemetryEngine",
    "emit_search_quant_observability_telemetry",
    "preflight_m2705_authorization",
]
