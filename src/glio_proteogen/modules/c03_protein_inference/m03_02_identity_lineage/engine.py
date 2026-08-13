"""Deterministic M03-02 protein-inference artifact-lineage reconciler."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_02.canonical import (
    canonical_request_digest,
    configuration_digest,
    normalized_request,
    policy_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_02.v1 import (
    M0302_CONTRACT_VERSION,
    ProteinInferenceIdentityLineageResolution,
    ProteinInferenceLineageReceipt,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
    derive_reconciliation,
    expected_limitations,
    expected_provenance,
    expected_support,
    expected_uncertainty,
    reconciliation_evidence_index,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceIdentityLineageResolution)
_AUTHORIZATION_MESSAGE: Final = (
    "protein-inference identity-lineage reconciliation requires accepted upstream controls"
)
_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)


class ProteinIdentityLineageAuthorizationError(ValueError):
    """Authorization failed before artifact or upstream-result traversal."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class M0302ProteinIdentityLineageReconciler:
    """Close a governed artifact DAG without inferring identity or scientific content."""

    __slots__ = ()

    def reconcile(self, request: object) -> ProteinInferenceIdentityLineageResolution:
        """Authorize, normalize, reconcile, and self-validate one immutable result."""

        preflight_protein_identity_lineage_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        canonical = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(normalized_request(validated)),
            strict=True,
        )

        graph, findings, disposition = derive_reconciliation(canonical)
        request_hash = canonical_request_digest(canonical)
        active_policy_hash = policy_digest(canonical.policy)
        configuration_hash = configuration_digest(canonical.policy)
        receipt = ProteinInferenceLineageReceipt(
            identity_resolution_digest=canonical.identity_resolution.resolution_digest,
            protocol_result_digest=canonical.protocol_result.result_digest,
            protocol_schema_digest=canonical.protocol_result.protocol_digest,
            search_space_digest=canonical.protocol_result.receipt.search_space_digest,
            policy_digest=active_policy_hash,
            configuration_digest=configuration_hash,
            graph_digest=graph.graph_digest,
            disposition=disposition,
        )
        payload: dict[str, object] = {
            "output_type": "protein_inference_identity_lineage_resolution",
            "result_id": f"result.m0302.{request_hash.removeprefix('sha256:')}",
            "result_version": M0302_CONTRACT_VERSION,
            "request_digest": request_hash,
            "identity_resolution_digest": canonical.identity_resolution.resolution_digest,
            "protocol_result_digest": canonical.protocol_result.result_digest,
            "policy_digest": active_policy_hash,
            "configuration_digest": configuration_hash,
            "graph_digest": graph.graph_digest,
            "result_digest": _DIGEST_SENTINEL,
            "request": canonical,
            "receipt": receipt,
            "graph": graph,
            "findings": findings,
            "disposition": disposition,
            "parent_target": "complex_activity",
            "emits_complex_activity": False,
            "infers_identity": False,
            "support": expected_support(disposition),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(canonical, request_hash, graph.graph_digest),
            "evidence": reconciliation_evidence_index(canonical),
            "limitations": expected_limitations(),
            "human_review_required": disposition is not ReconciliationDisposition.RECONCILED,
            "completed_at": canonical.context.occurred_at,
        }
        materialized = cast(
            "dict[str, Any]",
            # This is trusted, canonical engine output rather than public ingress;
            # applying the 4 MiB request parser cap here would make a valid maximum
            # request impossible to embed in its necessarily larger exact result.
            json.loads(canonical_json_bytes(payload)),
        )
        materialized["result_digest"] = result_payload_digest(materialized)
        return _RESULT_ADAPTER.validate_json(
            canonical_json_bytes(materialized),
            strict=True,
        )


def reconcile_protein_inference_identity_lineage(
    request: object,
) -> ProteinInferenceIdentityLineageResolution:
    """Public stateless M03-02 reconciliation entry point."""

    return M0302ProteinIdentityLineageReconciler().reconcile(request)


def preflight_protein_identity_lineage_authorization(candidate: object) -> None:
    """Fail closed using only the seven control states before protected traversal."""

    try:
        context = (
            candidate.context
            if isinstance(candidate, ReconcileProteinInferenceIdentityLineageRequest)
            else candidate.get("context")
            if isinstance(candidate, Mapping)
            else None
        )
        references = _member(context, "references")
        expected = (
            ("approved_configuration", "accepted"),
            ("identity_lineage", "resolved"),
            ("provenance", "accepted"),
            ("consent", "granted"),
            ("quality", "accepted"),
            ("support", "accepted"),
            ("intended_use", "accepted"),
        )
        authorized = all(
            _state_value(_member(_member(references, role), "state")) == state
            for role, state in expected
        )
    except Exception:  # noqa: BLE001 - fail closed at the hostile mapping boundary.
        raise ProteinIdentityLineageAuthorizationError from None
    if not authorized:
        raise ProteinIdentityLineageAuthorizationError


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


__all__ = [
    "M0302ProteinIdentityLineageReconciler",
    "ProteinIdentityLineageAuthorizationError",
    "preflight_protein_identity_lineage_authorization",
    "reconcile_protein_inference_identity_lineage",
]
