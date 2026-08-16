"""Deterministic M04-01 proteoform protocol-conformance evaluator."""

from __future__ import annotations

from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m04_01 import (
    M0401_CONTRACT_VERSION,
    EvaluateProteoformProtocolRequest,
    ProteoformProtocolConformanceDisposition,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolConformanceStatus,
    ProteoformProtocolFindingState,
    canonical_request_digest,
    configuration_digest,
    expected_limitations,
    expected_protocol_findings,
    expected_protocol_receipt,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    normalized_request,
    preflight_authorized,
    profile_digest,
    protocol_digest,
    protocol_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteoformProtocolRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformProtocolConformanceResult)
_AUTHORIZATION_MESSAGE: Final = "proteoform protocol evaluation requires accepted upstream controls"
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class ProteoformProtocolAuthorizationError(ValueError):
    """Authorization failed before protocol or profile material was traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M0401ProteoformProtocolEngine:
    """Evaluate one reviewed declaration without scientific inference."""

    __slots__ = ()

    def evaluate(self, request: object) -> ProteoformProtocolConformanceResult:
        preflight_proteoform_protocol_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )
        findings = expected_protocol_findings(
            canonical.protocol_schema,
            canonical.conformance_profile,
        )
        failed = any(item.state is ProteoformProtocolFindingState.FAIL for item in findings)
        disposition = (
            ProteoformProtocolConformanceDisposition.QUARANTINED
            if failed
            else ProteoformProtocolConformanceDisposition.CONFORMANT
        )
        status = (
            ProteoformProtocolConformanceStatus.NONCONFORMANT
            if failed
            else ProteoformProtocolConformanceStatus.CONFORMANT
        )
        request_hash = canonical_request_digest(canonical)
        receipt = expected_protocol_receipt(canonical)
        candidate = ProteoformProtocolConformanceResult.model_construct(
            result_id=f"result.m0401.{request_hash.removeprefix('sha256:')}",
            result_version=M0401_CONTRACT_VERSION,
            request_digest=request_hash,
            protocol_digest=protocol_digest(canonical.protocol_schema),
            profile_digest=profile_digest(canonical.conformance_profile),
            configuration_digest=configuration_digest(
                canonical.protocol_schema,
                canonical.conformance_profile,
            ),
            result_digest=_ZERO_DIGEST,
            request=canonical,
            receipt=receipt,
            findings=findings,
            status=status,
            disposition=disposition,
            parent_target="protein_rna_discordance",
            emits_protein_rna_discordance=False,
            emits_proteogenomic_state=False,
            emits_proteotype=False,
            emits_protein_level_subtype=False,
            infers_proteoform_or_isoform=False,
            infers_protein=False,
            infers_proteoform=False,
            infers_isoform=False,
            infers_glioma_specific_biology=False,
            localizes_modification=False,
            infers_kinase_activity=False,
            performs_all_omics_fusion=False,
            recommends_treatment=False,
            mutates_upstream_evidence=False,
            infers_identity_or_consent=False,
            support=expected_support(disposition),
            uncertainty=expected_uncertainty(),
            provenance=expected_provenance(canonical, receipt),
            evidence=protocol_evidence_index(canonical),
            limitations=expected_limitations(),
            human_review_required=failed,
            completed_at=canonical.context.occurred_at,
        )
        payload = candidate.model_dump(mode="python", by_alias=True, exclude_none=False)
        payload["result_digest"] = result_payload_digest(payload)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def evaluate_proteoform_protocol(
    request: object,
) -> ProteoformProtocolConformanceResult:
    """Evaluate one strict protocol/profile declaration through the public boundary."""

    return M0401ProteoformProtocolEngine().evaluate(request)


def preflight_proteoform_protocol_authorization(candidate: object) -> None:
    """Reject denied controls before protocol or profile material can be traversed."""

    try:
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = EvaluateProteoformProtocolRequest in candidate_mro or dict in candidate_mro
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _member(_member(references, role), "state") for role in expected}
        authorized = supported and states == expected
        if authorized:
            preflight_authorized(
                {
                    "context": {
                        "references": {role: {"state": state} for role, state in states.items()}
                    }
                }
            )
    except Exception:  # noqa: BLE001 - fail closed across caller-controlled objects.
        raise ProteoformProtocolAuthorizationError from None
    if not authorized:
        raise ProteoformProtocolAuthorizationError


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _plain_value(candidate: object) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        return {key: _plain_value(dict.__getitem__(mapping, key)) for key in dict.keys(mapping)}
    if list in candidate_mro:
        return [_plain_value(item) for item in list.__iter__(cast("list[object]", candidate))]
    if tuple in candidate_mro:
        values = cast("tuple[object, ...]", candidate)
        return tuple(_plain_value(item) for item in tuple.__iter__(values))
    return candidate


__all__ = [
    "M0401ProteoformProtocolEngine",
    "ProteoformProtocolAuthorizationError",
    "evaluate_proteoform_protocol",
    "preflight_proteoform_protocol_authorization",
]
