"""Canonical normalization and digest helpers for M03-02."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m01_02 import IdentityLineageResolution
from glio_proteogen.contracts.m01_02.canonical import normalized_resolution_payload
from glio_proteogen.contracts.m03_01 import ProteinInferenceProtocolConformanceResult
from glio_proteogen.contracts.m03_01.canonical import (
    normalized_result_payload as normalized_m0301_result_payload,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL = "sha256:" + ("0" * 64)


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", by_alias=True, exclude_none=False)
    return deepcopy(value)


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_derivation_methods"] = _sorted(data["approved_derivation_methods"])
    data["approved_cn_methods"] = _sorted(data["approved_cn_methods"])
    return data


def _normalized_identity_resolution(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        typed = cast("Any", value)
        data = normalized_resolution_payload(value)
        data["resolution_digest"] = typed.resolution_digest
        data["event_digest"] = typed.event_digest
        data["graph"]["graph_digest"] = typed.graph.graph_digest
        return data
    typed = IdentityLineageResolution.model_validate_json(
        canonical_json_bytes(value), strict=True
    )
    data = normalized_resolution_payload(typed)
    data["resolution_digest"] = typed.resolution_digest
    data["event_digest"] = typed.event_digest
    data["graph"]["graph_digest"] = typed.graph.graph_digest
    return data


def _normalized_protocol_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, BaseModel):
        value = ProteinInferenceProtocolConformanceResult.model_validate_json(
            canonical_json_bytes(value), strict=True
        )
    typed = cast("Any", value)
    data = normalized_m0301_result_payload(value)
    data["result_digest"] = typed.result_digest
    return data


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    if isinstance(value, BaseModel):
        typed = cast("Any", value)
        data["identity_resolution"] = _normalized_identity_resolution(
            typed.identity_resolution
        )
        data["protocol_result"] = _normalized_protocol_result(typed.protocol_result)
        data["policy"] = normalized_policy(typed.policy)
    else:
        data["identity_resolution"] = _normalized_identity_resolution(
            data["identity_resolution"]
        )
        data["protocol_result"] = _normalized_protocol_result(data["protocol_result"])
        data["policy"] = normalized_policy(data["policy"])
    for claim in data["artifact_claims"]:
        claim["declared_subject_component_ids"] = tuple(
            sorted(claim["declared_subject_component_ids"])
        )
    data["artifact_claims"] = _sorted(data["artifact_claims"])
    for derivation in data["derivations"]:
        derivation["source_claim_ids"] = tuple(sorted(derivation["source_claim_ids"]))
    data["derivations"] = _sorted(data["derivations"])
    data["cn_receipts"] = _sorted(data["cn_receipts"])
    return data


def normalized_graph_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["graph_digest"] = _DIGEST_SENTINEL
    data["artifacts"] = tuple(
        item.model_dump(mode="python", exclude_none=False)
        if isinstance(item, BaseModel)
        else item
        for item in data["artifacts"]
    )
    for node in data["artifacts"]:
        for field in (
            "declared_subject_component_ids",
            "resolved_subject_component_ids",
            "finding_codes",
        ):
            node[field] = tuple(sorted(node[field]))
    data["artifacts"] = _sorted(data["artifacts"])
    data["derivations"] = tuple(
        item.model_dump(mode="python", exclude_none=False)
        if isinstance(item, BaseModel)
        else item
        for item in data["derivations"]
    )
    for edge in data["derivations"]:
        edge["source_claim_ids"] = tuple(sorted(edge["source_claim_ids"]))
        edge["propagated_subject_component_ids"] = tuple(
            sorted(edge["propagated_subject_component_ids"])
        )
    data["derivations"] = _sorted(data["derivations"])
    return data


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["result_digest"] = _DIGEST_SENTINEL
    if isinstance(value, BaseModel):
        data["request"] = normalized_request(cast("Any", value).request)
    else:
        data["request"] = normalized_request(data["request"])
    data["graph"] = normalized_graph_payload(data["graph"])
    for finding in data["findings"]:
        finding["claim_ids"] = tuple(sorted(finding["claim_ids"]))
        finding["derivation_ids"] = tuple(sorted(finding["derivation_ids"]))
    data["findings"] = _sorted(data["findings"])
    data["provenance"]["input_digests"] = tuple(
        sorted(data["provenance"]["input_digests"])
    )
    data["provenance"]["control_decisions"] = _sorted(
        data["provenance"]["control_decisions"]
    )
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy_digest": policy_digest(value)})


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def resolved_graph_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_graph_payload(value))


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "normalized_graph_payload",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "resolved_graph_digest",
    "result_payload_digest",
]
