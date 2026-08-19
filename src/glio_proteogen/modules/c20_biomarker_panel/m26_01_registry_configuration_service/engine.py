"""Deterministic, caller-declared M26-01 registry runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_01 import (
    M2601_CONTRACT_VERSION,
    M2601_MODULE_ID,
    ProteinSubtypeRegistryResult,
    RegisterProteinSubtypeRegistryRequest,
    RegistryEntryStatus,
    RegistryFinding,
    RegistryFindingCode,
    RegistryRecord,
    RegistryStatus,
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

_REQUEST_ADAPTER: Final = TypeAdapter(RegisterProteinSubtypeRegistryRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeRegistryResult)
_ZERO_DIGEST: Final = "sha256:" + "0" * 64


class M2601AuthorizationError(ValueError):
    """Caller-declared controls do not authorize registry resolution."""

    def __init__(self) -> None:
        super().__init__(
            "M26-01 registry resolution requires accepted configuration, resolved identity, "
            "granted consent, and accepted provenance/quality/support/intended-use controls"
        )


class M2601ReplayError(ValueError):
    """A registry result failed canonical replay verification."""


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    state = _member(candidate, "state")
    return getattr(state, "value", state)


def preflight_m2601_authorization(candidate: object) -> None:
    """Fail closed on denied caller controls before registry material is read."""

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
            _state_value(_member(references, role)) == value for role, value in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings fail closed.
        raise M2601AuthorizationError from None
    if not authorized:
        raise M2601AuthorizationError


def _evidence(request: RegisterProteinSubtypeRegistryRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim="M26-01 registry source")
        for artifact in request.source_artifacts
    )


def _registry(request: RegisterProteinSubtypeRegistryRequest) -> RegistryRecord:
    return RegistryRecord(
        registry_id=request.registry_id,
        version=request.registry_version,
        entries=request.entries,
        history=request.history,
        lock_digest=sha256_digest({"entries": request.entries, "history": request.history}),
        evidence=_evidence(request),
    )


def _findings(
    request: RegisterProteinSubtypeRegistryRequest,
) -> tuple[RegistryFinding, ...]:
    by_id = {entry.entry_id: entry for entry in request.entries}
    findings: list[RegistryFinding] = []
    evidence = _evidence(request)
    for binding in request.active_configuration.bindings:
        entry = by_id[binding.entry_id]
        if entry.status is RegistryEntryStatus.QUARANTINED:
            findings.append(
                RegistryFinding(
                    finding_id="m2601.finding.quarantined." + entry.entry_id,
                    code=RegistryFindingCode.QUARANTINED_INPUT,
                    message=f"registry entry {entry.entry_id} is quarantined",
                    evidence=evidence,
                )
            )
        elif entry.status is not RegistryEntryStatus.ACTIVE:
            findings.append(
                RegistryFinding(
                    finding_id="m2601.finding.status." + entry.entry_id,
                    code=RegistryFindingCode.INCOMPATIBLE_CONFIGURATION,
                    message=f"registry entry {entry.entry_id} is not active",
                    evidence=evidence,
                )
            )
        if entry.compatibility_digest != binding.compatibility_digest:
            findings.append(
                RegistryFinding(
                    finding_id="m2601.finding.compatibility." + binding.binding_id,
                    code=RegistryFindingCode.INCOMPATIBLE_CONFIGURATION,
                    message=f"configuration binding {binding.binding_id} is incompatible",
                    evidence=evidence,
                )
            )
    if not findings:
        findings.append(
            RegistryFinding(
                finding_id="m2601.finding.provisional-review",
                code=RegistryFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Provisional registry ABI and caller authority require governed review.",
                evidence=evidence[:1],
            )
        )
    return tuple(findings)


def _uncertainty() -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"M26-01 does not estimate {dimension} uncertainty from registry material.",
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
            "Registry resolution does not estimate protein subtype biology or clinical "
            "uncertainty.",
        ),
    )


def _provenance(
    request: RegisterProteinSubtypeRegistryRequest, request_digest: str
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
        activity_id="m2601.activity." + request_digest.removeprefix("sha256:"),
        actor_id=request.context.actor_id,
        module_id=M2601_MODULE_ID,
        module_version=M2601_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(artifact.digest for artifact in request.source_artifacts),
        configuration_digest=sha256_digest(request.active_configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


class M2601RegistryEngine:
    """Resolve one immutable registry and active configuration projection."""

    __slots__ = ()

    def register(self, request: object) -> ProteinSubtypeRegistryResult:
        preflight_m2601_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(validated.model_dump(mode="json")), strict=True
        )
        request_digest = canonical_request_digest(canonical)
        evidence = _evidence(canonical)
        findings = _findings(canonical)
        abstained = any(
            item.code
            in {
                RegistryFindingCode.QUARANTINED_INPUT,
                RegistryFindingCode.INCOMPATIBLE_CONFIGURATION,
            }
            for item in findings
        )
        registry = None if abstained else _registry(canonical)
        payload: dict[str, Any] = {
            "result_id": result_identifier(request_digest),
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "request_digest": request_digest,
            "status": RegistryStatus.ABSTAINED if abstained else RegistryStatus.REGISTERED,
            "registry": registry,
            "active_configuration": None if abstained else canonical.active_configuration,
            "findings": findings,
            "abstention_reason": (
                "active configuration is unresolved or incompatible" if abstained else None
            ),
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if abstained else SupportStatus.SUPPORTED,
                reason_code="registry_configuration_review" if abstained else "registry_registered",
                rationale=(
                    "Registry material was retained but cannot be activated safely."
                    if abstained
                    else (
                        "Caller-declared registry and active configuration were "
                        "structurally resolved."
                    )
                ),
            ),
            "uncertainty": _uncertainty(),
            "provenance": _provenance(canonical, request_digest),
            "evidence": evidence,
            "limitations": (
                Limitation(
                    code="caller_declared_authority",
                    statement=(
                        "Issuer authority and registry signatures are caller-declared "
                        "and unauthenticated."
                    ),
                ),
                Limitation(
                    code="registry_only",
                    statement=(
                        "The service resolves registry/configuration metadata and emits "
                        "no protein subtype claim."
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
        provisional = ProteinSubtypeRegistryResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(provisional)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def replay(self, result: ProteinSubtypeRegistryResult) -> ProteinSubtypeRegistryResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
            if validated.request_digest != canonical_request_digest(validated.request):
                raise M2601ReplayError  # noqa: TRY301
            if validated.result_id != result_identifier(validated.request_digest):
                raise M2601ReplayError  # noqa: TRY301
            if validated.result_digest != result_payload_digest(validated):
                raise M2601ReplayError  # noqa: TRY301
            expected = self.register(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M2601ReplayError  # noqa: TRY301
        except M2601ReplayError:
            raise
        except Exception as error:
            raise M2601ReplayError from error
        return validated


def register_protein_subtype_registry(request: object) -> ProteinSubtypeRegistryResult:
    """Public stateless M26-01 registration entry point."""

    return M2601RegistryEngine().register(request)


__all__ = [
    "M2601AuthorizationError",
    "M2601RegistryEngine",
    "M2601ReplayError",
    "preflight_m2601_authorization",
    "register_protein_subtype_registry",
]
