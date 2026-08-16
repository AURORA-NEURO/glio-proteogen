"""Deterministic M05-07 PTM-localization support and abstention routing."""

# The engine has one bounded receipt builder and intentionally fail-closed exception
# branches; keeping those local makes the public boundary easier to audit.
# ruff: noqa: TRY301, PLR0913

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_07 import (
    M0507_CONTRACT_VERSION,
    M0507_EVIDENCE_CLAIM,
    M0507_MAX_CANONICAL_REQUEST_BYTES,
    M0507_MODULE_ID,
    PtmLocalizationAbstentionCode,
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationRemediationPath,
    PtmLocalizationSupportDimension,
    PtmLocalizationSupportDisposition,
    PtmLocalizationSupportFact,
    PtmLocalizationSupportReceipt,
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
    canonical_request_digest,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(RoutePtmLocalizationSupportRequest)
_AUTHORIZATION_MESSAGE: Final = "M05-07 support routing requires accepted upstream controls"
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_CONTROL_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_REMEDIATION_BY_DECISION: Final = {
    PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN: (
        PtmLocalizationRemediationPath.CORRECT_SUPPORT_DECLARATION,
    ),
    PtmLocalizationDimensionSupportDecision.INDETERMINATE: (
        PtmLocalizationRemediationPath.SUPPLY_REQUIRED_SUPPORT_EVIDENCE,
    ),
}
_LIMITATIONS: Final = (
    Limitation(
        code="support_routing_only",
        statement=(
            "M05-07 emits a support-domain decision only; it does not emit a negative "
            "scientific finding, variant peptide, proteotype, or treatment advice."
        ),
    ),
    Limitation(
        code="caller_declared_controls",
        statement=(
            "Upstream controls, policy, and evidence are caller-declared and their issuers "
            "are not authenticated by this module."
        ),
    ),
)


class PtmLocalizationSupportAuthorizationError(PermissionError):
    """Authorization failed before support facts were traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PtmLocalizationSupportInputError(ValueError):
    """A candidate request failed closed without reflecting caller payloads."""

    def __init__(self) -> None:
        super().__init__("M05-07 request failed strict validation")


class _SerializedRequestTooLargeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-07 canonical request exceeds its byte limit")


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_text(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def _plain_value(value: object) -> object:
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if type(value) is list:
        return [_plain_value(item) for item in cast("list[object]", value)]
    if type(value) is dict:
        result: dict[str, object] = {}
        for key, item in cast("dict[object, object]", value).items():
            if type(key) is not str:
                raise PtmLocalizationSupportInputError
            result[key] = _plain_value(item)
        return result
    raise PtmLocalizationSupportInputError


def preflight_ptm_localization_support_authorization(candidate: object) -> None:
    """Reject denied controls before opening policy, prerequisites, or facts."""

    if type(candidate) is not RoutePtmLocalizationSupportRequest and not isinstance(
        candidate, Mapping
    ):
        raise PtmLocalizationSupportAuthorizationError
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise PtmLocalizationSupportAuthorizationError from None
    if states != _EXPECTED_CONTROL_STATES:
        raise PtmLocalizationSupportAuthorizationError


def _validate_json_request(
    candidate: object, serialized: bytes | str
) -> RoutePtmLocalizationSupportRequest:
    """Strictly parse one JSON request after authorization preflight."""

    if not isinstance(candidate, Mapping):
        raise PtmLocalizationSupportInputError
    preflight_ptm_localization_support_authorization(candidate)
    try:
        canonical = canonical_json_bytes(_plain_value(candidate))
        if len(canonical) > M0507_MAX_CANONICAL_REQUEST_BYTES:
            raise _SerializedRequestTooLargeError
        strict_json_loads(serialized, max_bytes=M0507_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    except PtmLocalizationSupportAuthorizationError:
        raise
    except _SerializedRequestTooLargeError:
        raise
    except Exception as error:
        raise PtmLocalizationSupportInputError from error


def _prepare_request(candidate: object) -> RoutePtmLocalizationSupportRequest:
    if type(candidate) is RoutePtmLocalizationSupportRequest:
        preflight_ptm_localization_support_authorization(candidate)
        raw = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(raw) > M0507_MAX_CANONICAL_REQUEST_BYTES:
            raise _SerializedRequestTooLargeError
        return _REQUEST_ADAPTER.validate_json(raw, strict=True)
    if isinstance(candidate, Mapping):
        preflight_ptm_localization_support_authorization(candidate)
        raw = canonical_json_bytes(_plain_value(candidate))
        return _validate_json_request(candidate, raw)
    raise PtmLocalizationSupportInputError


class M0507PtmLocalizationSupportEngine:
    """Route declared support facts without I/O, mutation, or learned inference."""

    __slots__ = ()

    def route(self, request: object) -> PtmLocalizationSupportRouteResult:
        return self._route_validated(_prepare_request(request))

    @staticmethod
    def _route_validated(
        request: RoutePtmLocalizationSupportRequest,
    ) -> PtmLocalizationSupportRouteResult:
        request_hash = canonical_request_digest(request)
        unsupported = tuple(
            fact.dimension
            for fact in request.declared_facts
            if fact.decision is not PtmLocalizationDimensionSupportDecision.SUPPORTED
        )
        disposition = (
            PtmLocalizationSupportDisposition.SUPPORTED
            if not unsupported
            else PtmLocalizationSupportDisposition.ABSTAINED
        )
        code = _abstention_code(request.declared_facts) if unsupported else None
        remediation = _remediation(request.declared_facts) if unsupported else ()
        receipt = _build_receipt(
            request_hash,
            disposition,
            code,
            remediation,
            unsupported,
            _evidence(request),
        )
        result_values: dict[str, object] = {
            "output_type": "ptm_localization_support_route",
            "result_id": f"result.m0507.{request_hash.removeprefix('sha256:')}",
            "result_version": M0507_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "receipt": receipt,
            "support_decision": _support_decision(disposition),
            "disposition": disposition,
            "abstention_code": code,
            "remediation": remediation,
            "parent_target": "variant_peptide",
            "emits_parent": False,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _LIMITATIONS,
        }
        result_values["result_digest"] = result_payload_digest(
            PtmLocalizationSupportRouteResult.model_construct(**cast("Any", result_values))
        )
        return PtmLocalizationSupportRouteResult(**cast("Any", result_values))


def route_ptm_localization_support(request: object) -> PtmLocalizationSupportRouteResult:
    """Stateless public M05-07 operation."""

    return M0507PtmLocalizationSupportEngine().route(request)


def _abstention_code(
    facts: tuple[PtmLocalizationSupportFact, ...],
) -> PtmLocalizationAbstentionCode:
    if any(
        item.decision is PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN for item in facts
    ):
        return PtmLocalizationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
    return PtmLocalizationAbstentionCode.DIMENSION_INDETERMINATE


def _remediation(
    facts: tuple[PtmLocalizationSupportFact, ...],
) -> tuple[PtmLocalizationRemediationPath, ...]:
    paths: list[PtmLocalizationRemediationPath] = []
    for fact in facts:
        if fact.decision is not PtmLocalizationDimensionSupportDecision.SUPPORTED:
            for path in _REMEDIATION_BY_DECISION[fact.decision]:
                if path not in paths:
                    paths.append(path)
    return tuple(paths)


def _build_receipt(
    request_hash: str,
    disposition: PtmLocalizationSupportDisposition,
    code: PtmLocalizationAbstentionCode | None,
    remediation: tuple[PtmLocalizationRemediationPath, ...],
    unsupported: tuple[PtmLocalizationSupportDimension, ...],
    evidence: tuple[EvidenceReference, ...],
) -> PtmLocalizationSupportReceipt:
    values: dict[str, object] = {
        "request_digest": request_hash,
        "disposition": disposition,
        "abstention_code": code,
        "remediation": remediation,
        "unsupported_dimensions": unsupported,
        "evidence": evidence,
        "receipt_digest": _ZERO_DIGEST,
    }
    values["receipt_digest"] = receipt_digest(
        PtmLocalizationSupportReceipt.model_construct(**cast("Any", values))
    )
    return PtmLocalizationSupportReceipt(**cast("Any", values))


def _support_decision(disposition: PtmLocalizationSupportDisposition) -> SupportDecision:
    if disposition is PtmLocalizationSupportDisposition.SUPPORTED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="support_domain_supported",
            rationale="Every declared support dimension is supported.",
        )
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="support_domain_abstained",
        rationale="At least one declared support dimension requires abstention or review.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    estimate = _not_estimable(M0507_EVIDENCE_CLAIM)
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=_not_estimable("Upstream identification uncertainty is not re-estimated."),
        support=_not_estimable("Support is categorical within the declared support domain."),
        transport=_not_estimable("Transport beyond the reviewed support domain is not estimable."),
        sensitivity_notes=(
            "Missing and unknown evidence are indeterminate and never negative.",
            "Outside-domain evidence abstains and receives a remediation path.",
        ),
    )


def _evidence(request: RoutePtmLocalizationSupportRequest) -> tuple[EvidenceReference, ...]:
    evidence = [item for fact in request.declared_facts for item in fact.evidence]
    evidence.append(
        EvidenceReference(
            reference=request.prerequisites.harmonization_result,
            role="evidence",
            claim="M05-06 harmonization prerequisite is bound by media type.",
        )
    )
    return tuple(evidence[:16])


def _provenance(
    request: RoutePtmLocalizationSupportRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = (
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
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in controls
    )
    return ProvenanceRecord(
        activity_id=f"activity.m0507.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0507_MODULE_ID,
        module_version=M0507_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.prerequisites.harmonization_result.digest,
            *(_fact_digest(fact) for fact in request.declared_facts),
        ),
        configuration_digest=request.policy.evidence.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _fact_digest(fact: PtmLocalizationSupportFact) -> str:
    return canonical_request_digest(fact)


__all__ = [
    "M0507PtmLocalizationSupportEngine",
    "PtmLocalizationSupportAuthorizationError",
    "PtmLocalizationSupportInputError",
    "_validate_json_request",
    "preflight_ptm_localization_support_authorization",
    "route_ptm_localization_support",
]
