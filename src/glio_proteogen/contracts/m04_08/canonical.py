"""Semantic canonicalization for the M04-08 release-package spine."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    return value.model_dump(mode="python", by_alias=True, exclude_none=False)


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_artifact(artifact: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(artifact)


def artifact_digest(artifact: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_artifact(artifact))


def normalized_policy(policy: BaseModel | dict[str, Any]) -> dict[str, Any]:
    value = _dump(policy)
    value["allowed_signature_algorithms"] = sorted(value["allowed_signature_algorithms"])
    value["allowed_verifier_ids"] = sorted(value["allowed_verifier_ids"])
    return value


def policy_digest(policy: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def normalized_reproduction_evidence(
    evidence: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    return _dump(evidence)


def reproduction_evidence_digest(evidence: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_reproduction_evidence(evidence))


def context_digest(context: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(_dump(context))


def normalized_manifest(manifest: BaseModel | dict[str, Any]) -> dict[str, Any]:
    value = _dump(manifest)
    value["artifacts"] = _sort(value["artifacts"])
    for stage in value["stages"]:
        stage["bound_upstream_result_digests"] = sorted(stage["bound_upstream_result_digests"])
    value["software_versions"] = _sort(value["software_versions"])
    value["reference_versions"] = _sort(value["reference_versions"])
    return value


def manifest_digest(manifest: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_manifest(manifest))


def signing_statement_digest(  # noqa: PLR0913 - exact domain-separated statement.
    *,
    active_manifest_digest: str,
    active_policy_digest: str,
    release_id: str,
    release_version: str,
    identity_resolution_digest: str,
    intended_use_evidence_digest: str,
    terminal_routing_result_digest: str,
) -> Sha256Digest:
    """Bind the external signature statement without circular receipt inclusion."""

    return sha256_digest(
        {
            "domain": "GLIO-PROTEOGEN-M04-08:proteoform-release:v1",
            "module_id": "GLIO-PROTEOGEN-M04-08",
            "contract_version": "1.0.0",
            "manifest_digest": active_manifest_digest,
            "policy_digest": active_policy_digest,
            "release_id": release_id,
            "release_version": release_version,
            "identity_resolution_digest": identity_resolution_digest,
            "intended_use_evidence_digest": intended_use_evidence_digest,
            "terminal_routing_result_digest": terminal_routing_result_digest,
        }
    )


def normalized_request(request: BaseModel | dict[str, Any]) -> dict[str, Any]:
    value = _dump(request)
    value["artifacts"] = _sort([normalized_artifact(item) for item in value["artifacts"]])
    value["software_versions"] = _sort(value["software_versions"])
    value["reference_versions"] = _sort(value["reference_versions"])
    value["reproduction_evidence"] = normalized_reproduction_evidence(
        value["reproduction_evidence"]
    )
    value["policy"] = normalized_policy(value["policy"])
    return value


def canonical_request_digest(request: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel | dict[str, Any]) -> dict[str, Any]:
    value = _dump(result)
    value.pop("result_digest", None)
    value["policy"] = normalized_policy(value["policy"])
    value["manifest"] = normalized_manifest(value["manifest"])
    value["quarantine_reasons"] = _sort(value["quarantine_reasons"])
    if value["package_descriptor"] is not None:
        value["package_descriptor"]["members"] = _sort(value["package_descriptor"]["members"])
    value["provenance"]["input_digests"] = sorted(value["provenance"]["input_digests"])
    value["provenance"]["control_decisions"] = _sort(value["provenance"]["control_decisions"])
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


normalized_result = normalized_result_payload


def result_payload_digest(result: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "artifact_digest",
    "canonical_request_digest",
    "context_digest",
    "manifest_digest",
    "normalized_artifact",
    "normalized_manifest",
    "normalized_policy",
    "normalized_reproduction_evidence",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "policy_digest",
    "reproduction_evidence_digest",
    "result_payload_digest",
    "signing_statement_digest",
]
