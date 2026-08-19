"""Deterministic M04-02 proteoform identity-lineage reconciler."""

from __future__ import annotations

from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m01_02 import IdentityLineageResolution
from glio_proteogen.contracts.m04_01 import ProteoformProtocolConformanceResult
from glio_proteogen.contracts.m04_02 import (
    M0402_CONTRACT_VERSION,
    ProteoformIdentityLineageResolution,
    ProteoformLineageDisposition,
    ReconcileProteoformIdentityLineageRequest,
    canonical_request_digest,
    configuration_digest,
    derive_proteoform_reconciliation,
    expected_limitations,
    expected_provenance,
    expected_receipt,
    expected_support,
    expected_uncertainty,
    normalized_request,
    policy_digest,
    proteoform_lineage_evidence_index,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteoformIdentityLineageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteoformIdentityLineageResolution)
_IDENTITY_ADAPTER: Final = TypeAdapter(IdentityLineageResolution)
_PROTOCOL_ADAPTER: Final = TypeAdapter(ProteoformProtocolConformanceResult)
_AUTHORIZATION_MESSAGE: Final = (
    "proteoform identity-lineage reconciliation requires accepted upstream controls"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_STATE_TYPES: Final = (
    str,
    UpstreamDecisionState,
    IdentityLineageState,
    ConsentState,
)
_MAX_PLAIN_DEPTH: Final = 72
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 150_000
_MAX_PLAIN_SEQUENCE: Final = 4_096


class ProteoformIdentityLineageAuthorizationError(ValueError):
    """Authorization failed before upstream results or lineage material were traversed."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-02 strict request values require bounded built-in containers")


class M0402ProteoformIdentityLineageReconciler:
    """Close one governed physical/artifact graph without inferring identity."""

    __slots__ = ()

    def reconcile(self, request: object) -> ProteoformIdentityLineageResolution:
        """Authorize, strictly replay, reconcile, and seal one immutable result."""

        preflight_proteoform_identity_lineage_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )

        # These explicit public replays make the upstream trust boundary visible and
        # reject model_construct or re-signed nested forgeries independently of receipts.
        _IDENTITY_ADAPTER.validate_python(canonical.identity_resolution, strict=True)
        _PROTOCOL_ADAPTER.validate_python(canonical.protocol_result, strict=True)

        graph, findings, disposition = derive_proteoform_reconciliation(canonical)
        request_hash = canonical_request_digest(canonical)
        active_policy_hash = policy_digest(canonical.policy)
        configuration_hash = configuration_digest(canonical.policy)
        receipt = expected_receipt(canonical, graph, disposition, findings=findings)
        payload: dict[str, object] = {
            "output_type": "proteoform_identity_lineage_resolution",
            "result_id": f"result.m0402.{request_hash.removeprefix('sha256:')}",
            "result_version": M0402_CONTRACT_VERSION,
            "request_digest": request_hash,
            "identity_resolution_digest": canonical.identity_resolution.resolution_digest,
            "protocol_result_digest": canonical.protocol_result.result_digest,
            "policy_digest": active_policy_hash,
            "configuration_digest": configuration_hash,
            "graph_digest": graph.graph_digest,
            "result_digest": _ZERO_DIGEST,
            "request": canonical,
            "receipt": receipt,
            "graph": graph,
            "findings": findings,
            "disposition": disposition,
            "parent_target": "protein_rna_discordance",
            "emits_protein_rna_discordance": False,
            "emits_proteogenomic_state": False,
            "emits_proteotype": False,
            "emits_protein_level_subtype": False,
            "infers_identity": False,
            "infers_consent": False,
            "infers_protein": False,
            "infers_proteoform": False,
            "infers_isoform": False,
            "infers_glioma_specific_biology": False,
            "infers_kinase_activity": False,
            "performs_cn_to_protein_regression": False,
            "performs_all_omics_fusion": False,
            "recommends_treatment": False,
            "mutates_upstream": False,
            "support": expected_support(disposition),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(canonical, request_hash, graph.graph_digest),
            "evidence": proteoform_lineage_evidence_index(canonical),
            "limitations": expected_limitations(),
            "human_review_required": (disposition is not ProteoformLineageDisposition.RECONCILED),
            "completed_at": canonical.context.occurred_at,
        }
        payload["result_digest"] = result_payload_digest(payload)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def reconcile_proteoform_identity_lineage(
    request: object,
) -> ProteoformIdentityLineageResolution:
    """Public stateless M04-02 reconciliation entry point."""

    return M0402ProteoformIdentityLineageReconciler().reconcile(request)


def preflight_proteoform_identity_lineage_authorization(candidate: object) -> None:
    """Fail closed on seven controls before touching governed lineage material."""

    authorized = False
    try:
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = (
            ReconcileProteoformIdentityLineageRequest in candidate_mro or dict in candidate_mro
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
    except Exception:  # noqa: BLE001 - fail closed across caller-controlled objects.
        raise ProteoformIdentityLineageAuthorizationError from None
    if not authorized:
        raise ProteoformIdentityLineageAuthorizationError


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    if candidate_type in _STATE_TYPES[1:]:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    """Copy bounded built-in containers before strict Pydantic validation.

    The request can arrive as a caller-controlled mapping or a model constructed
    outside Pydantic's normal lifecycle.  Bound traversal before validation so
    recursive/cyclic values fail as typed input errors instead of exhausting the
    interpreter or spending unbounded work in this boundary.
    """

    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
        if dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(storage)
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
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
    return candidate


__all__ = [
    "M0402ProteoformIdentityLineageReconciler",
    "ProteoformIdentityLineageAuthorizationError",
    "preflight_proteoform_identity_lineage_authorization",
    "reconcile_proteoform_identity_lineage",
]
