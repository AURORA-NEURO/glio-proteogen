"""Semantic canonicalization for M05-02 identity-lineage contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.contracts.m01_02.canonical import (
    normalized_resolution_payload as normalized_m0102_resolution_payload,
)
from glio_proteogen.contracts.m05_01 import (
    normalized_result_payload as normalized_m0501_result_payload,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Identifier, Sha256Digest

_ZERO_DIGEST = "sha256:" + ("0" * 64)


def _python(value: Any) -> Any:  # noqa: ANN401 - recursive canonical JSON shape.
    if isinstance(value, BaseModel):
        return _python(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, dict):
        return {key: _python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_python(item) for item in value)
    return deepcopy(value)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return dict(_python(value))


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_identity_resolution(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Canonicalize the embedded, already-digest-bound M01-02 result."""

    source = _dump(value)
    if isinstance(value, BaseModel):
        data = normalized_m0102_resolution_payload(value)
    else:
        # Public M01-02 normalization accepts a model. Dict inputs reach this helper only
        # after M05-02 strict validation, so normalize their semantic collections here.
        data = source
        for component in data["components"]:
            component["member_entity_ids"] = _sorted(component["member_entity_ids"])
            component["subject_component_ids"] = _sorted(component["subject_component_ids"])
        data["components"] = _sorted(data["components"])
        for node in data["graph"]["nodes"]:
            node["subject_component_ids"] = _sorted(node["subject_component_ids"])
        data["graph"]["nodes"] = _sorted(data["graph"]["nodes"])
        for operation in data["graph"]["operations"]:
            operation["source_entity_ids"] = _sorted(operation["source_entity_ids"])
            operation["target_entity_ids"] = _sorted(operation["target_entity_ids"])
        data["graph"]["operations"] = _sorted(data["graph"]["operations"])
        for disposition in data["assertion_dispositions"]:
            disposition["evidence"] = _sorted(disposition["evidence"])
        data["assertion_dispositions"] = _sorted(data["assertion_dispositions"])
        for issue in data["issues"]:
            for field in (
                "entity_ids",
                "component_ids",
                "operation_ids",
                "assertion_ids",
                "evidence",
            ):
                issue[field] = _sorted(issue[field])
        data["issues"] = _sorted(data["issues"])
        data["provenance"]["input_digests"] = _sorted(data["provenance"]["input_digests"])
        data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
        data["evidence"] = _sorted(data["evidence"])
        data["limitations"] = _sorted(data["limitations"])
        data["uncertainty"]["sensitivity_notes"] = _sorted(data["uncertainty"]["sensitivity_notes"])
    data["resolution_digest"] = source["resolution_digest"]
    data["event_digest"] = source["event_digest"]
    data["graph"]["graph_digest"] = source["graph"]["graph_digest"]
    return data


def normalized_protocol_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Canonicalize the embedded, already-digest-bound M05-01 result."""

    data = normalized_m0501_result_payload(value)
    data["result_digest"] = _dump(value)["result_digest"]
    return data


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_configurations"] = _sorted(data["approved_configurations"])
    data["approved_derivation_methods"] = _sorted(data["approved_derivation_methods"])
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy_digest": policy_digest(value)})


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["identity_resolution"] = normalized_identity_resolution(data["identity_resolution"])
    data["protocol_result"] = normalized_protocol_result(data["protocol_result"])
    data["policy"] = normalized_policy(data["policy"])
    for claim in data["artifact_claims"]:
        claim["declared_subject_component_ids"] = _sorted(claim["declared_subject_component_ids"])
    data["artifact_claims"] = _sorted(data["artifact_claims"])
    for derivation in data["derivations"]:
        derivation["source_claim_ids"] = _sorted(derivation["source_claim_ids"])
    data["derivations"] = _sorted(data["derivations"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def physical_lineage_path_digest(
    identity_resolution: BaseModel | dict[str, Any],
    entity_id: Identifier,
) -> Sha256Digest:
    """Hash the exact governed physical ancestry subgraph for one anchor."""

    data = normalized_identity_resolution(identity_resolution)
    nodes = {node["entity_id"]: node for node in data["graph"]["nodes"]}
    if entity_id not in nodes:
        raise ValueError("physical lineage path anchor is absent from the identity graph")
    operations = tuple(data["graph"]["operations"])
    ancestors = {entity_id}
    selected: list[dict[str, Any]] = []
    changed = True
    while changed:
        changed = False
        for operation in operations:
            if set(operation["target_entity_ids"]) & ancestors and operation not in selected:
                selected.append(operation)
                before = len(ancestors)
                ancestors.update(operation["source_entity_ids"])
                changed = changed or len(ancestors) != before
    return sha256_digest(
        {
            "identity_resolution_digest": data["resolution_digest"],
            "anchor_entity_id": entity_id,
            "nodes": _sorted(tuple(nodes[item] for item in ancestors)),
            "operations": _sorted(selected),
        }
    )


def normalized_graph_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["graph_digest"] = _ZERO_DIGEST
    for artifact in data["artifacts"]:
        artifact["declared_subject_component_ids"] = _sorted(
            artifact["declared_subject_component_ids"]
        )
        artifact["resolved_subject_component_ids"] = _sorted(
            artifact["resolved_subject_component_ids"]
        )
        artifact["finding_codes"] = _sorted(artifact["finding_codes"])
    data["artifacts"] = _sorted(data["artifacts"])
    for derivation in data["derivations"]:
        derivation["source_claim_ids"] = _sorted(derivation["source_claim_ids"])
        derivation["propagated_subject_component_ids"] = _sorted(
            derivation["propagated_subject_component_ids"]
        )
    data["derivations"] = _sorted(data["derivations"])
    return data


def resolved_graph_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_graph_payload(value))


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["finding_codes"] = _sorted(data["finding_codes"])
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    receipt_source = data["receipt"]
    data["receipt"] = normalized_receipt(receipt_source)
    data["receipt"]["receipt_digest"] = receipt_source["receipt_digest"]
    data["graph"] = normalized_graph_payload(data["graph"])
    data["graph"]["graph_digest"] = _dump(value)["graph"]["graph_digest"]
    for finding in data["findings"]:
        finding["claim_ids"] = _sorted(finding["claim_ids"])
        finding["derivation_ids"] = _sorted(finding["derivation_ids"])
    data["findings"] = _sorted(data["findings"])
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["provenance"]["input_digests"] = _sorted(data["provenance"]["input_digests"])
    data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
    data["uncertainty"]["sensitivity_notes"] = _sorted(data["uncertainty"]["sensitivity_notes"])
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "normalized_graph_payload",
    "normalized_identity_resolution",
    "normalized_policy",
    "normalized_protocol_result",
    "normalized_receipt",
    "normalized_request",
    "normalized_result_payload",
    "physical_lineage_path_digest",
    "policy_digest",
    "receipt_digest",
    "resolved_graph_digest",
    "result_payload_digest",
]
