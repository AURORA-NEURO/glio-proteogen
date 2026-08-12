"""Semantic canonicalization for the M02-08 identification release closure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


class _RequestLike(Protocol):
    @property
    def operation(self) -> str: ...

    @property
    def contract_version(self) -> str: ...

    @property
    def context(self) -> BaseModel: ...

    @property
    def release_id(self) -> str: ...

    @property
    def release_version(self) -> str: ...

    @property
    def artifacts(self) -> tuple[BaseModel, ...]: ...

    @property
    def software_versions(self) -> tuple[BaseModel, ...]: ...

    @property
    def reference_versions(self) -> tuple[BaseModel, ...]: ...

    @property
    def reproduction_evidence(self) -> BaseModel: ...

    @property
    def policy(self) -> BaseModel: ...

    @property
    def signature(self) -> BaseModel: ...

    @property
    def supersedes_result_digest(self) -> str | None: ...


def _dump(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="python", by_alias=True, exclude_none=False)


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_artifact(artifact: BaseModel) -> dict[str, Any]:
    return _dump(artifact)


def artifact_digest(artifact: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_artifact(artifact))


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = _dump(policy)
    value["allowed_signature_algorithms"] = sorted(value["allowed_signature_algorithms"])
    value["allowed_verifier_ids"] = sorted(value["allowed_verifier_ids"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def reproduction_evidence_digest(evidence: BaseModel) -> Sha256Digest:
    return sha256_digest(_dump(evidence))


def context_digest(context: BaseModel) -> Sha256Digest:
    return sha256_digest(_dump(context))


def normalized_manifest(manifest: BaseModel) -> dict[str, Any]:
    value = _dump(manifest)
    value.pop("manifest_digest", None)
    value["artifacts"] = _sort(value["artifacts"])
    # stages are an ordered M02-01 -> M02-07 transformation chain and stay ordered.
    for stage in value["stages"]:
        stage["bound_upstream_result_digests"] = sorted(stage["bound_upstream_result_digests"])
    value["software_versions"] = _sort(value["software_versions"])
    value["reference_versions"] = _sort(value["reference_versions"])
    return value


def manifest_digest(manifest: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_manifest(manifest))


def signing_statement_digest(  # noqa: PLR0913 - exact domain-separated statement.
    *,
    active_manifest_digest: str,
    active_policy_digest: str,
    release_id: str,
    release_version: str,
    subject_binding_digest: str,
    intended_use_evidence_digest: str,
) -> Sha256Digest:
    """Bind a signature without including the signature in the manifest."""

    return sha256_digest(
        {
            "domain": "GLIO-PROTEOGEN-M02-08:identification-release:v1",
            "module_id": "GLIO-PROTEOGEN-M02-08",
            "contract_version": "1.0.0",
            "manifest_digest": active_manifest_digest,
            "policy_digest": active_policy_digest,
            "release_id": release_id,
            "release_version": release_version,
            "subject_binding_digest": subject_binding_digest,
            "intended_use_evidence_digest": intended_use_evidence_digest,
        }
    )


def normalized_request(request: _RequestLike) -> dict[str, Any]:
    return {
        "operation": request.operation,
        "contract_version": request.contract_version,
        "context": _dump(request.context),
        "release_id": request.release_id,
        "release_version": request.release_version,
        "artifacts": _sort([normalized_artifact(item) for item in request.artifacts]),
        "software_versions": _sort([_dump(item) for item in request.software_versions]),
        "reference_versions": _sort([_dump(item) for item in request.reference_versions]),
        "reproduction_evidence": _dump(request.reproduction_evidence),
        "policy": normalized_policy(request.policy),
        "signature": _dump(request.signature),
        "supersedes_result_digest": request.supersedes_result_digest,
    }


def canonical_request_digest(request: _RequestLike) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = _dump(result)
    value.pop("result_digest", None)
    value["policy"] = normalized_policy(result.policy)  # type: ignore[attr-defined]
    value["manifest"] = normalized_manifest(result.manifest)  # type: ignore[attr-defined]
    value["quarantine_reasons"] = _sort(value["quarantine_reasons"])
    if value["package_descriptor"] is not None:
        value["package_descriptor"]["members"] = _sort(value["package_descriptor"]["members"])
    value["provenance"]["input_digests"] = sorted(value["provenance"]["input_digests"])
    value["provenance"]["control_decisions"] = _sort(value["provenance"]["control_decisions"])
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "artifact_digest",
    "canonical_request_digest",
    "context_digest",
    "manifest_digest",
    "normalized_artifact",
    "normalized_manifest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "policy_digest",
    "reproduction_evidence_digest",
    "result_payload_digest",
    "signing_statement_digest",
]
