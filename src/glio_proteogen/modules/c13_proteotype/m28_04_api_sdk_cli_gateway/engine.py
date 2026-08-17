"""Deterministic, caller-declared M28-04 gateway runtime."""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m28_04 import (
    M2804_CONTRACT_VERSION,
    M2804_MODULE_ID,
    AccessSurface,
    AuthorizationDecision,
    GatewayFinding,
    GatewayFindingCode,
    GatewayStatus,
    JobStatus,
    OperationStatus,
    ProteinRnaDiscordanceAccessSurfaceResult,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(PublishProteinRnaDiscordanceAccessSurfaceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceAccessSurfaceResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64


class M2804AuthorizationError(ValueError):
    """Caller-declared controls do not authorize gateway publication."""

    def __init__(self) -> None:
        super().__init__(
            "M28-04 gateway publication requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2804ReplayError(ValueError):
    """A gateway result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return candidate.get(field)
    if isinstance(candidate, BaseModel):
        return getattr(candidate, field, None)
    return None


def _state_value(candidate: object) -> object:
    state = _member(candidate, "state")
    return getattr(state, "value", state)


def preflight_m2804_authorization(candidate: object) -> None:
    """Fail closed on all seven caller controls before gateway traversal."""

    if type(candidate) is not dict and not isinstance(candidate, BaseModel):
        raise M2804AuthorizationError
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
        raise M2804AuthorizationError from None
    if not authorized:
        raise M2804AuthorizationError


def _validate_request(candidate: object) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
    if isinstance(candidate, (bytes, bytearray, str)):
        decoded = strict_json_loads(candidate)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    if type(candidate) is dict:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(candidate)), strict=True)
    if isinstance(candidate, PublishProteinRnaDiscordanceAccessSurfaceRequest):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise TypeError from None


def _evidence(
    request: PublishProteinRnaDiscordanceAccessSurfaceRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M28-04 gateway source artifact.",
        )
        for artifact in request.source_artifacts
    )


def _surface(request: PublishProteinRnaDiscordanceAccessSurfaceRequest) -> AccessSurface:
    return AccessSurface(
        surface_id="m2804.surface." + request.configuration.configuration_id,
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
    request: PublishProteinRnaDiscordanceAccessSurfaceRequest,
) -> tuple[GatewayFinding, ...]:
    evidence = _evidence(request)
    findings: list[GatewayFinding] = []
    for authorization in request.authorizations:
        if authorization.decision is not AuthorizationDecision.ALLOW:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2804.finding.authorization." + authorization.authorization_id,
                    code=GatewayFindingCode.OPERATION_UNAUTHORIZED,
                    message=f"operation {authorization.operation_id} is not authorized",
                    evidence=evidence,
                )
            )
    for operation in request.operations:
        if operation.status is OperationStatus.DISABLED:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2804.finding.operation." + operation.operation_id,
                    code=GatewayFindingCode.OPERATION_UNAUTHORIZED,
                    message=f"operation {operation.operation_id} is disabled",
                    evidence=evidence,
                )
            )
    for job in request.jobs:
        if job.status is not JobStatus.SUCCEEDED:
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2804.finding.job." + job.job_id,
                    code=GatewayFindingCode.ASYNC_JOB_UNBOUND,
                    message=f"async job {job.job_id} is not successfully resolved",
                    evidence=evidence,
                )
            )
    for rule in request.compatibility_rules:
        if rule.status.value != "compatible":
            findings.append(  # noqa: PERF401 - preserves typed finding order.
                GatewayFinding(
                    finding_id="m2804.finding.compatibility." + rule.rule_id,
                    code=GatewayFindingCode.COMPATIBILITY_UNRESOLVED,
                    message=f"compatibility rule {rule.rule_id} requires review",
                    evidence=evidence,
                )
            )
    if not findings:
        findings.append(
            GatewayFinding(
                finding_id="m2804.finding.provisional-review",
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
            rationale=f"M28-04 does not estimate {dimension} uncertainty from gateway material.",
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
            "Gateway publication does not estimate protein-RNA discordance biology or clinical "
            "uncertainty.",
        ),
    )


def _provenance(
    request: PublishProteinRnaDiscordanceAccessSurfaceRequest, request_digest: str
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
        activity_id="m2804.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2804_MODULE_ID,
        module_version=M2804_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


class M2804GatewayEngine:
    """Publish one deterministic API/SDK/CLI gateway access surface."""

    __slots__ = ()

    def publish(self, request: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        preflight_m2804_authorization(request)
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
                        "The service publishes typed access metadata and emits no protein-RNA "
                        "discordance claim."
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
        provisional = ProteinRnaDiscordanceAccessSurfaceResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2804ReplayError  # noqa: TRY301
            if validated.result_id != result_identifier(validated.request_digest):
                raise M2804ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2804ReplayError  # noqa: TRY301
            expected = self.publish(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2804ReplayError  # noqa: TRY301
        except M2804ReplayError:
            raise
        except Exception as error:
            raise M2804ReplayError from error
        return validated


def publish_protein_rna_discordance_access_surface(
    request: object,
) -> ProteinRnaDiscordanceAccessSurfaceResult:
    """Public stateless M28-04 gateway publication entry point."""

    return M2804GatewayEngine().publish(request)


__all__ = [
    "M2804AuthorizationError",
    "M2804GatewayEngine",
    "M2804ReplayError",
    "preflight_m2804_authorization",
    "publish_protein_rna_discordance_access_surface",
]
