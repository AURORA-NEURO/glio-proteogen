"""Deterministic M05-02 PTM-localization identity-lineage engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m01_02 import IdentityLineageResolution
from glio_proteogen.contracts.m05_01 import PtmLocalizationProtocolConformanceResult
from glio_proteogen.contracts.m05_02 import (
    M0502_CONTRACT_VERSION,
    M0502_MAX_ARTIFACT_CLAIMS,
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    M0502_MAX_SUBJECT_COMPONENT_IDS,
    PtmLocalizationIdentityLineagePolicy,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageDisposition,
    ReconcilePtmLocalizationIdentityLineageRequest,
    canonical_request_digest,
    configuration_digest,
    derive_ptm_localization_reconciliation,
    expected_limitations,
    expected_provenance,
    expected_receipt,
    expected_support,
    expected_uncertainty,
    policy_digest,
    ptm_localization_configuration_is_supported,
    ptm_localization_lineage_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, IdentityLineageState, UpstreamDecisionState

_AUTHORIZATION_MESSAGE: Final = (
    "PTM-localization identity-lineage reconciliation requires accepted upstream controls"
)
_REQUEST_ADAPTER: Final = TypeAdapter(ReconcilePtmLocalizationIdentityLineageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(PtmLocalizationIdentityLineageResolution)
_IDENTITY_ADAPTER: Final = TypeAdapter(IdentityLineageResolution)
_PROTOCOL_ADAPTER: Final = TypeAdapter(PtmLocalizationProtocolConformanceResult)
_POLICY_ADAPTER: Final = TypeAdapter(PtmLocalizationIdentityLineagePolicy)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_PLAIN_DEPTH: Final = 72
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 150_000
_MAX_PLAIN_SEQUENCE: Final = max(M0502_MAX_ARTIFACT_CLAIMS, M0502_MAX_SUBJECT_COMPONENT_IDS)
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "identity_resolution",
        "protocol_result",
        "policy",
        "artifact_claims",
        "derivations",
        "supersedes_result_digest",
    }
)
_PREFIX_FIELDS: Final = (
    "operation",
    "contract_version",
    "request_id",
    "context",
    "identity_resolution",
    "protocol_result",
    "policy",
    "supersedes_result_digest",
)
_STATE_TYPES: Final = (UpstreamDecisionState, IdentityLineageState, ConsentState)


class PtmLocalizationIdentityLineageAuthorizationError(PermissionError):
    """Authorization failed before upstream results or artifact claims were traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PtmLocalizationIdentityLineageInputError(ValueError):
    """An authorized request failed strict validation without reflecting caller content."""

    def __init__(self) -> None:
        super().__init__("M05-02 request failed strict validation")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-02 strict request values require exact built-in containers")


class _SerializedRequestTooLargeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-02 canonical request exceeds its byte limit")


class M0502Engine:
    """Replay governed inputs and emit only the immutable resolution and graph envelope."""

    __slots__ = ()

    def reconcile(self, request: object) -> PtmLocalizationIdentityLineageResolution:
        validated = _validate_prepared_request(_prepare_request_candidate(request))
        return self._reconcile_validated(validated)

    @staticmethod
    def _reconcile_validated(
        request: ReconcilePtmLocalizationIdentityLineageRequest,
    ) -> PtmLocalizationIdentityLineageResolution:
        graph, findings, disposition = derive_ptm_localization_reconciliation(request)
        request_hash = canonical_request_digest(request)
        active_policy_hash = policy_digest(request.policy)
        local_configuration_hash = configuration_digest(request.policy)
        receipt = expected_receipt(request, graph, disposition, findings=findings)
        payload: dict[str, object] = {
            "output_type": "ptm_localization_identity_lineage_resolution",
            "result_id": f"result.m0502.{request_hash.removeprefix('sha256:')}",
            "result_version": M0502_CONTRACT_VERSION,
            "request_digest": request_hash,
            "identity_resolution_digest": request.identity_resolution.resolution_digest,
            "protocol_result_digest": request.protocol_result.result_digest,
            "policy_digest": active_policy_hash,
            "configuration_digest": local_configuration_hash,
            "graph_digest": graph.graph_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "receipt": receipt,
            "graph": graph,
            "findings": findings,
            "disposition": disposition,
            "parent_target": "variant_peptide",
            "emits_variant_peptide": False,
            "emits_proteogenomic_state": False,
            "emits_proteotype": False,
            "emits_protein_level_subtype": False,
            "infers_identity": False,
            "infers_consent": False,
            "infers_protein": False,
            "infers_ptm_localization": False,
            "infers_kinase_activity": False,
            "performs_cn_to_protein_regression": False,
            "performs_all_omics_fusion": False,
            "recommends_treatment": False,
            "mutates_upstream": False,
            "support": expected_support(disposition),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash, graph.graph_digest),
            "evidence": ptm_localization_lineage_evidence_index(request),
            "limitations": expected_limitations(),
            "human_review_required": (
                disposition is not PtmLocalizationLineageDisposition.RECONCILED
            ),
            "completed_at": request.context.occurred_at,
        }
        payload["result_digest"] = result_payload_digest(payload)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def reconcile_ptm_localization_identity_lineage(
    request: object,
) -> PtmLocalizationIdentityLineageResolution:
    """Public stateless M05-02 operation."""

    return M0502Engine().reconcile(request)


def preflight_ptm_localization_identity_lineage_authorization(candidate: object) -> None:
    """Check seven controls before touching identity, protocol, policy, or claim material."""

    try:
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = (
            ReconcilePtmLocalizationIdentityLineageRequest in candidate_mro or dict in candidate_mro
        )
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
        states = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
        authorized = supported and states == expected
    except Exception:  # noqa: BLE001 - hostile ordinary exceptions fail closed.
        raise PtmLocalizationIdentityLineageAuthorizationError from None
    if not authorized:
        raise PtmLocalizationIdentityLineageAuthorizationError


def _prepare_request_candidate(candidate: object) -> dict[str, object]:
    preflight_ptm_localization_identity_lineage_authorization(candidate)
    prepared: dict[str, object]
    try:
        _validate_outer_request_shape(candidate)
        budget = [_MAX_PLAIN_NODES]
        prepared = {
            field: _plain_value(_member(candidate, field), _budget=budget)
            for field in _PREFIX_FIELDS
            if field != "supersedes_result_digest" or _member(candidate, field) is not None
        }
        identity = _IDENTITY_ADAPTER.validate_json(
            canonical_json_bytes(prepared["identity_resolution"]), strict=True
        )
        protocol = _PROTOCOL_ADAPTER.validate_json(
            canonical_json_bytes(prepared["protocol_result"]), strict=True
        )
        policy = _POLICY_ADAPTER.validate_json(
            canonical_json_bytes(prepared["policy"]), strict=True
        )
        traversable = (
            identity.decision.value == "resolved"
            and protocol.disposition.value == "conformant"
            and ptm_localization_configuration_is_supported(protocol, policy)
        )
        if traversable:
            prepared["artifact_claims"] = _plain_value(
                _member(candidate, "artifact_claims"), _budget=budget
            )
            prepared["derivations"] = _plain_value(
                _member(candidate, "derivations"), _budget=budget
            )
        else:
            prepared["artifact_claims"] = ()
            prepared["derivations"] = ()
    except _InvalidPlainValueError:
        raise
    except Exception:  # noqa: BLE001 - never reflect nested caller content.
        raise PtmLocalizationIdentityLineageInputError from None
    return prepared


def _validate_prepared_request(
    prepared: dict[str, object],
) -> ReconcilePtmLocalizationIdentityLineageRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(prepared), strict=True)
    except Exception:  # noqa: BLE001 - never reflect nested caller content.
        raise PtmLocalizationIdentityLineageInputError from None


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ReconcilePtmLocalizationIdentityLineageRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0502_MAX_CANONICAL_REQUEST_BYTES:
        raise _SerializedRequestTooLargeError
    return _validate_prepared_request(_prepare_request_candidate(candidate))


def _validate_outer_request_shape(candidate: object) -> None:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if ReconcilePtmLocalizationIdentityLineageRequest in candidate_mro:
        return
    if dict not in candidate_mro:
        raise PtmLocalizationIdentityLineageInputError
    mapping = cast("dict[object, object]", candidate)
    _validate_plain_mapping(mapping)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise PtmLocalizationIdentityLineageInputError


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return dict.get(mapping, field)
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return dict.get(storage, field)
    return None


def _validate_plain_mapping(mapping: dict[object, object]) -> None:
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    if candidate_type in _STATE_TYPES:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return {
            key: _plain_value(dict.__getitem__(storage, key), _depth=_depth + 1, _budget=budget)
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return {
            key: _plain_value(dict.__getitem__(mapping, key), _depth=_depth + 1, _budget=budget)
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        if type(value) is not str:
            raise _InvalidPlainValueError
        return value
    return candidate


__all__ = [
    "M0502Engine",
    "PtmLocalizationIdentityLineageAuthorizationError",
    "PtmLocalizationIdentityLineageInputError",
    "preflight_ptm_localization_identity_lineage_authorization",
    "reconcile_ptm_localization_identity_lineage",
]
