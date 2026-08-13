"""Semantic canonicalization for M03-03 raw-source admission."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest

_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_COMPLEX_BUNDLE_ROLE: Final = "complex_activity_input_bundle"


def _json_shape(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return one canonical-JSON primitive shape for typed/dict public parity."""

    from glio_proteogen.kernel.strict_json import strict_json_loads  # noqa: PLC0415

    decoded = strict_json_loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):  # pragma: no cover - public model roots are objects.
        raise TypeError("M03-03 canonical object root must be a mapping")
    return decoded


def _sort(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(values, key=canonical_json_bytes))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize the reviewed policy's semantically unordered build sets."""

    data = _json_shape(value)
    data["approved_genome_builds"] = _sort(data["approved_genome_builds"])
    data["approved_transcript_builds"] = _sort(data["approved_transcript_builds"])
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    """Bind the active M03-03 configuration to exactly one reviewed policy."""

    return sha256_digest({"protein_inference_raw_policy": normalized_policy(value)})


def normalized_protocol_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    """Normalize a projected M03-01 receipt while retaining every upstream digest."""

    return _json_shape(value)


def normalized_protocol_receipt_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    """Return the non-recursive payload used to derive a protocol receipt digest."""

    data = normalized_protocol_receipt(value)
    data.pop("receipt_digest", None)
    return data


def protocol_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_protocol_receipt_payload(value))


def normalized_lineage_artifact(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    data = _json_shape(value)
    data["finding_codes"] = tuple(sorted(data["finding_codes"]))
    return data


def normalized_lineage_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    """Normalize the unordered M03-02 artifact projection and preserve its graph digests."""

    data = _json_shape(value)
    data["artifacts"] = _sort(
        tuple(normalized_lineage_artifact(item) for item in data["artifacts"])
    )
    return data


def normalized_lineage_receipt_payload(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    """Return the non-recursive payload used to derive a lineage receipt digest."""

    data = normalized_lineage_receipt(value)
    data.pop("receipt_digest", None)
    return data


def lineage_receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_lineage_receipt_payload(value))


def normalized_source(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize one source declaration without inspecting or embedding raw payload bytes."""

    return _json_shape(value)


def normalized_sources(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return _sort(tuple(normalized_source(item) for item in values))


def normalized_source_manifest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Normalize declarations participating in the non-circular source manifest."""

    declarations = tuple(normalized_source(item) for item in values)
    return _sort(tuple(item for item in declarations if item["role"] != _COMPLEX_BUNDLE_ROLE))


def canonical_source_manifest_digest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> Sha256Digest:
    return sha256_digest(normalized_source_manifest(values))


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize every unordered M03-03 request collection with typed/dict parity."""

    data = _json_shape(value)
    data["protocol_receipt"] = normalized_protocol_receipt(data["protocol_receipt"])
    data["lineage_receipt"] = normalized_lineage_receipt(data["lineage_receipt"])
    data["policy"] = normalized_policy(data["policy"])
    data["sources"] = normalized_sources(data["sources"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def normalized_diagnostic(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _json_shape(value)
    data["source_ids"] = tuple(sorted(data["source_ids"]))
    return data


def normalized_raw_input(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _json_shape(value)
    data["diagnostics"] = _sort(tuple(normalized_diagnostic(item) for item in data["diagnostics"]))
    return data


def normalized_admission_receipt(
    value: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    return _json_shape(value)


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize the complete result and replace its recursive digest with a sentinel."""

    data = _json_shape(value)
    data["result_digest"] = _DIGEST_SENTINEL
    data["request"] = normalized_request(data["request"])
    data["receipt"] = normalized_admission_receipt(data["receipt"])
    data["raw_inputs"] = _sort(tuple(normalized_raw_input(item) for item in data["raw_inputs"]))
    data["diagnostics"] = _sort(tuple(normalized_diagnostic(item) for item in data["diagnostics"]))
    data["provenance"]["input_digests"] = tuple(sorted(data["provenance"]["input_digests"]))
    data["provenance"]["control_decisions"] = _sort(data["provenance"]["control_decisions"])
    data["evidence"] = _sort(data["evidence"])
    data["limitations"] = _sort(data["limitations"])
    data["uncertainty"]["sensitivity_notes"] = tuple(
        sorted(data["uncertainty"]["sensitivity_notes"])
    )
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "canonical_request_digest",
    "canonical_source_manifest_digest",
    "configuration_digest",
    "lineage_receipt_digest",
    "normalized_admission_receipt",
    "normalized_diagnostic",
    "normalized_lineage_artifact",
    "normalized_lineage_receipt",
    "normalized_lineage_receipt_payload",
    "normalized_policy",
    "normalized_protocol_receipt",
    "normalized_protocol_receipt_payload",
    "normalized_raw_input",
    "normalized_request",
    "normalized_result_payload",
    "normalized_source",
    "normalized_source_manifest",
    "normalized_sources",
    "policy_digest",
    "protocol_receipt_digest",
    "result_payload_digest",
]
