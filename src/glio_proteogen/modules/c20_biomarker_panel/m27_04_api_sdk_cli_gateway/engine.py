"""Deterministic, caller-declared M27-04 gateway runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_04 import (
    M2704_CONTRACT_VERSION,
    M2704_MODULE_ID,
    AccessSurface,
    AuthorizationDecision,
    ComplexActivityAccessSurfaceResult,
    GatewayFinding,
    GatewayFindingCode,
    GatewayStatus,
    JobStatus,
    OperationStatus,
    PublishComplexActivityAccessSurfaceRequest,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishComplexActivityAccessSurfaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityAccessSurfaceResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64


class M2704AuthorizationError(ValueError):
    """Caller-declared controls do not authorize gateway publication."""

    def __init__(self) -> None:
        super().__init__(
            "M27-04 gateway publication requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2704ReplayError(ValueError):
    """A gateway result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    state = _member(candidate, "state")
    return getattr(state, "value", state)


def preflight_m2704_authorization(candidate: object) -> None:
    """Fail closed on all seven caller controls before gateway traversal."""

    try:
        context = _member(candidate, "context")
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
        raise M2704AuthorizationError from None
    if not authorized:
        raise M2704AuthorizationError


def _validate_request(candidate: object) -> PublishComplexActivityAccessSurfaceRequest:
    if isinstance(candidate, (bytes, bytearray, str)):
        decoded = strict_json_loads(candidate)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(candidate)), strict=True)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _evidence(
    request: PublishComplexActivityAccessSurfaceRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M27-04 gateway source artifact.",
        )
        for artifact in request.source_artifacts
    )


def _surface(request: PublishComplexActivityAccessSurfaceRequest) -> AccessSurface:
    return AccessSurface(
        surface_id="m2704.surface." + request.configuration.configuration_id,
        version=request.configuration.version,
        operations=request.operations,
        authorizations=request.authorizations,
        idempotency_records=request.idempotency_records,
        jobs=request.jobs,
        compatibility_rules=request.compatibility_rules,
        errors=request.errors,
        audit_events=request.audit_events,
        configuration=request.configuration,
        evidence=_evidence(request),
    )


def _findings(
    request: PublishComplexActivityAccessSurfaceRequest,
) -> tuple[GatewayFinding, ...]:
    evidence = _evidence(request)
    findings: list[GatewayFinding] = []
    for authorization in request.authorizations:
        if authorization.decision is not AuthorizationDecision.ALLOW:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2704.finding.authorization." + authorization.authorization_id,
                    code=GatewayFindingCode.OPERATION_UNAUTHORIZED,
                    message=f"operation {authorization.operation_id} is not authorized",
                    evidence=evidence,
                )
            )
    for operation in request.operations:
        if operation.status is OperationStatus.DISABLED:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2704.finding.operation." + operation.operation_id,
                    code=GatewayFindingCode.OPERATION_UNAUTHORIZED,
                    message=f"operation {operation.operation_id} is disabled",
                    evidence=evidence,
                )
            )
    for job in request.jobs:
        if job.status is not JobStatus.SUCCEEDED:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2704.finding.job." + job.job_id,
                    code=GatewayFindingCode.ASYNC_JOB_UNBOUND,
                    message=f"async job {job.job_id} is not successfully resolved",
                    evidence=evidence,
                )
            )
    for rule in request.compatibility_rules:
        if rule.status.value != "compatible":
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2704.finding.compatibility." + rule.rule_id,
                    code=GatewayFindingCode.COMPATIBILITY_UNRESOLVED,
                    message=f"compatibility rule {rule.rule_id} requires review",
                    evidence=evidence,
                )
            )
    if not findings:
        findings.append(
            GatewayFinding(
                finding_id="m2704.finding.provisional-review",
                code=GatewayFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Provisional gateway ABI and caller authority require governed review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M27-04 does not estimate {dimension} uncertainty from gateway material.",
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
            "Gateway publication does not estimate complex activity biology or clinical "
            "uncertainty.",
        ),
    )


def _provenance(
    request: PublishComplexActivityAccessSurfaceRequest, request_digest: str
) -> ProvenanceRecord:
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
        activity_id="m2704.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2704_MODULE_ID,
        module_version=M2704_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


class M2704GatewayEngine:
    """Publish one deterministic API/SDK/CLI gateway access surface."""

    __slots__ = ()

    def publish(self, request: object) -> ComplexActivityAccessSurfaceResult:
        preflight_m2704_authorization(request)
        canonical = _validate_request(request)
        request_digest = canonical_request_digest(canonical)
        evidence = _evidence(canonical)
        findings = _findings(canonical)
        blocking_codes = {
            GatewayFindingCode.OPERATION_UNAUTHORIZED,
            GatewayFindingCode.ASYNC_JOB_UNBOUND,
            GatewayFindingCode.COMPATIBILITY_UNRESOLVED,
        }
        blocking = any(finding.code in blocking_codes for finding in findings)
        payload: dict[str, Any] = {
            "result_id": result_identifier(request_digest),
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "request_digest": request_digest,
            "status": GatewayStatus.ABSTAINED if blocking else GatewayStatus.PUBLISHED,
            "access_surface": None if blocking else _surface(canonical),
            "findings": findings,
            "abstention_reason": (
                "gateway authorization, job, or compatibility material is unresolved"
                if blocking
                else None
            ),
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if blocking else SupportStatus.SUPPORTED,
                reason_code="gateway_material_review" if blocking else "gateway_published",
                rationale=(
                    "Gateway material was retained but cannot be published safely."
                    if blocking
                    else "Caller-declared gateway operations were structurally resolved."
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(
                    code="caller_declared_authority",
                    statement=(
                        "Issuer authority and gateway signatures are caller-declared "
                        "and unauthenticated."
                    ),
                ),
                Limitation(
                    code="access_surface_only",
                    statement=(
                        "The service publishes typed access metadata and emits no complex "
                        "activity claim."
                    ),
                ),
                Limitation(
                    code="human_review_required",
                    statement=(
                        "Human review remains required for provisional ABI confirmation "
                        "and exceptions."
                    ),
                ),
            ),
            "human_review_required": True,
        }
        provisional = ComplexActivityAccessSurfaceResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: object) -> ComplexActivityAccessSurfaceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2704ReplayError  # noqa: TRY301
            if validated.result_id != result_identifier(validated.request_digest):
                raise M2704ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2704ReplayError  # noqa: TRY301
            expected = self.publish(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2704ReplayError  # noqa: TRY301
        except M2704ReplayError:
            raise
        except Exception as error:
            raise M2704ReplayError from error
        return validated


def publish_complex_activity_access_surface(
    request: object,
) -> ComplexActivityAccessSurfaceResult:
    """Public stateless M27-04 gateway publication entry point."""

    return M2704GatewayEngine().publish(request)


__all__ = [
    "M2704AuthorizationError",
    "M2704GatewayEngine",
    "M2704ReplayError",
    "preflight_m2704_authorization",
    "publish_complex_activity_access_surface",
]
