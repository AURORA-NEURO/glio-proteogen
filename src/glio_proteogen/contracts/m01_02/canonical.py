"""Semantic canonicalization for M01-02 identity and lineage contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def _normalize_artifacts(record: dict[str, Any], field: str = "evidence") -> None:
    if field in record:
        record[field] = _sort(record[field])


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    """Normalize the one semantically unordered policy collection."""

    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["allowed_operation_kinds"] = _sort(value["allowed_operation_kinds"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    """Return the active identity-policy content digest."""

    return sha256_digest(normalized_policy(policy))


def normalized_request(request: BaseModel) -> dict[str, Any]:
    """Normalize every unordered request collection without removing duplicates."""

    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["policy"]["allowed_operation_kinds"] = _sort(
        value["policy"]["allowed_operation_kinds"]
    )
    for entity in value["entities"]:
        entity["identity_tokens"] = _sort(entity["identity_tokens"])
        _normalize_artifacts(entity)
    value["entities"] = _sort(value["entities"])
    for assertion in value["assertions"]:
        if assertion["assertion_type"] in {"same_as", "different_from"}:
            assertion["left_entity_id"], assertion["right_entity_id"] = sorted(
                (assertion["left_entity_id"], assertion["right_entity_id"])
            )
        _normalize_artifacts(assertion)
    value["assertions"] = _sort(value["assertions"])
    for operation in value["lineage_operations"]:
        operation["source_entity_ids"] = _sort(operation["source_entity_ids"])
        operation["target_entity_ids"] = _sort(operation["target_entity_ids"])
        for channel in operation["channels"]:
            _normalize_artifacts(channel)
        operation["channels"] = _sort(operation["channels"])
        _normalize_artifacts(operation)
    value["lineage_operations"] = _sort(value["lineage_operations"])
    for observation in value["concordance_observations"]:
        observation["left_entity_id"], observation["right_entity_id"] = sorted(
            (observation["left_entity_id"], observation["right_entity_id"])
        )
        _normalize_artifacts(observation)
    value["concordance_observations"] = _sort(value["concordance_observations"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    """Hash a request after domain-specific order normalization."""

    return sha256_digest(normalized_request(request))


def normalized_evidence_manifest(request: BaseModel) -> list[dict[str, Any]]:
    """List every submitted evidence attachment without private token or channel material."""

    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    entries: list[dict[str, Any]] = []

    def add(
        owner_type: str,
        owner_id: str,
        attachment_role: str,
        artifacts: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> None:
        entries.extend(
            {
                "owner_type": owner_type,
                "owner_id": owner_id,
                "attachment_role": attachment_role,
                "artifact": artifact,
            }
            for artifact in artifacts
        )

    references = value["context"]["references"]
    for role in sorted(references):
        add("control", role, "decision_evidence", (references[role]["evidence"],))
    for entity in value["entities"]:
        entity_id = entity["entity_id"]
        add("entity", entity_id, "entity_evidence", entity["evidence"])
        for token in entity["identity_tokens"]:
            token_scope = "|".join(
                str(token[field])
                for field in (
                    "issuer_id",
                    "namespace_id",
                    "scope_id",
                    "key_id",
                    "token_version",
                    "entity_kind",
                )
            )
            add("identity_token", entity_id, token_scope, (token["evidence"],))
    for assertion in value["assertions"]:
        add(
            "identity_assertion",
            assertion["assertion_id"],
            assertion["assertion_type"],
            assertion["evidence"],
        )
    for operation in value["lineage_operations"]:
        operation_id = operation["operation_id"]
        add("lineage_operation", operation_id, operation["kind"], operation["evidence"])
        for channel in operation["channels"]:
            add(
                "demultiplex_channel",
                operation_id,
                channel["channel_id"],
                channel["evidence"],
            )
    for observation in value["concordance_observations"]:
        add(
            "concordance_observation",
            observation["observation_id"],
            observation["classification"],
            observation["evidence"],
        )
    return _sort(entries)


def evidence_manifest_digest(request: BaseModel) -> Sha256Digest:
    """Bind every evidence attachment while excluding token and channel-tag secrets."""

    return sha256_digest(normalized_evidence_manifest(request))


def normalized_graph(graph: BaseModel) -> dict[str, Any]:
    """Normalize a privacy-minimized resolved graph."""

    value = graph.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("graph_digest", None)
    for node in value["nodes"]:
        node["subject_component_ids"] = _sort(node["subject_component_ids"])
    value["nodes"] = _sort(value["nodes"])
    for operation in value["operations"]:
        operation["source_entity_ids"] = _sort(operation["source_entity_ids"])
        operation["target_entity_ids"] = _sort(operation["target_entity_ids"])
    value["operations"] = _sort(value["operations"])
    return value


def graph_digest(graph: BaseModel) -> Sha256Digest:
    """Hash only the privacy-minimized resolved graph semantics."""

    return sha256_digest(normalized_graph(graph))


def normalized_resolution_payload(resolution: BaseModel) -> dict[str, Any]:
    """Normalize a resolution while excluding its own and ledger event digests."""

    value = resolution.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("resolution_digest", None)
    value.pop("event_digest", None)
    for component in value["components"]:
        component["member_entity_ids"] = _sort(component["member_entity_ids"])
        component["subject_component_ids"] = _sort(component["subject_component_ids"])
    value["components"] = _sort(value["components"])
    graph = value["graph"]
    graph.pop("graph_digest", None)
    for node in graph["nodes"]:
        node["subject_component_ids"] = _sort(node["subject_component_ids"])
    graph["nodes"] = _sort(graph["nodes"])
    for operation in graph["operations"]:
        operation["source_entity_ids"] = _sort(operation["source_entity_ids"])
        operation["target_entity_ids"] = _sort(operation["target_entity_ids"])
    graph["operations"] = _sort(graph["operations"])
    for disposition in value["assertion_dispositions"]:
        _normalize_artifacts(disposition)
    value["assertion_dispositions"] = _sort(value["assertion_dispositions"])
    for issue in value["issues"]:
        issue["entity_ids"] = _sort(issue["entity_ids"])
        issue["component_ids"] = _sort(issue["component_ids"])
        issue["operation_ids"] = _sort(issue["operation_ids"])
        issue["assertion_ids"] = _sort(issue["assertion_ids"])
        _normalize_artifacts(issue)
    value["issues"] = _sort(value["issues"])
    value["provenance"]["input_digests"] = _sort(value["provenance"]["input_digests"])
    value["provenance"]["control_decisions"] = _sort(
        value["provenance"]["control_decisions"]
    )
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


def resolution_payload_digest(resolution: BaseModel) -> Sha256Digest:
    """Hash all public resolution semantics except self-referential ledger digests."""

    return sha256_digest(normalized_resolution_payload(resolution))


_CORE_FIELDS = (
    "resolution_id",
    "resolution_version",
    "request_digest",
    "policy_digest",
    "decision",
    "components",
    "graph",
    "assertion_dispositions",
    "concordance",
    "issues",
    "human_review_required",
    "resolved_at",
    "supersedes_resolution_digest",
)


def normalized_resolution_core(resolution: BaseModel) -> dict[str, Any]:
    """Normalize only pure reconciliation semantics shared by draft and service output."""

    payload = resolution.model_dump(mode="python", by_alias=True, exclude_none=False)
    value = {field: payload[field] for field in _CORE_FIELDS}
    for component in value["components"]:
        component["member_entity_ids"] = _sort(component["member_entity_ids"])
        component["subject_component_ids"] = _sort(component["subject_component_ids"])
    value["components"] = _sort(value["components"])
    graph = value["graph"]
    graph.pop("graph_digest", None)
    for node in graph["nodes"]:
        node["subject_component_ids"] = _sort(node["subject_component_ids"])
    graph["nodes"] = _sort(graph["nodes"])
    for operation in graph["operations"]:
        operation["source_entity_ids"] = _sort(operation["source_entity_ids"])
        operation["target_entity_ids"] = _sort(operation["target_entity_ids"])
    graph["operations"] = _sort(graph["operations"])
    for disposition in value["assertion_dispositions"]:
        _normalize_artifacts(disposition)
    value["assertion_dispositions"] = _sort(value["assertion_dispositions"])
    for issue in value["issues"]:
        issue["entity_ids"] = _sort(issue["entity_ids"])
        issue["component_ids"] = _sort(issue["component_ids"])
        issue["operation_ids"] = _sort(issue["operation_ids"])
        issue["assertion_ids"] = _sort(issue["assertion_ids"])
        _normalize_artifacts(issue)
    value["issues"] = _sort(value["issues"])
    return value


def resolution_core_digest(resolution: BaseModel) -> Sha256Digest:
    """Hash pure reconciliation semantics without service or ledger envelope material."""

    return sha256_digest(normalized_resolution_core(resolution))


__all__ = [
    "canonical_request_digest",
    "evidence_manifest_digest",
    "graph_digest",
    "normalized_evidence_manifest",
    "normalized_graph",
    "normalized_policy",
    "normalized_request",
    "normalized_resolution_core",
    "normalized_resolution_payload",
    "policy_digest",
    "resolution_core_digest",
    "resolution_payload_digest",
]
