"""Semantic canonicalization for M04-03 raw-input ingestion contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from glio_proteogen.contracts.m04_02 import (
    normalized_result_payload as normalized_m0402_result_payload,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

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


def normalized_parser(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return one parser profile's stable semantic payload."""

    return _dump(value)


def parser_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_parser(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_parsers"] = _sorted(data["approved_parsers"])
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy_digest": policy_digest(value)})


def normalized_artifact(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def artifact_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_artifact(value))


def artifact_mapping_digest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> Sha256Digest:
    """Bind the complete canonical four-role artifact mapping."""

    return sha256_digest(_sorted(tuple(normalized_artifact(item) for item in values)))


def normalized_document(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    if "localization_states" in data:
        data["localization_states"] = _sorted(data["localization_states"])
    return data


def document_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_document(value))


def normalized_lineage_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = normalized_m0402_result_payload(value)
    data["result_digest"] = _dump(value)["result_digest"]
    return data


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["lineage_result"] = normalized_lineage_result(data["lineage_result"])
    data["policy"] = normalized_policy(data["policy"])
    data["artifacts"] = _sorted(data["artifacts"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def context_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    data = _dump(value)
    context = data.get("context", data)
    return sha256_digest(context)


def normalized_validated_input(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["document"] = normalized_document(data["document"])
    data["diagnostic_codes"] = _sorted(data["diagnostic_codes"])
    return data


def validated_input_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_validated_input(value))


def validated_inputs_digest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> Sha256Digest:
    """Bind the canonical zero-or-four validated-input region."""

    return sha256_digest(_sorted(tuple(normalized_validated_input(item) for item in values)))


def normalized_diagnostic(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def diagnostic_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_diagnostic(value))


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["diagnostic_codes"] = _sorted(data["diagnostic_codes"])
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    source = _dump(value)
    data = deepcopy(source)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    data["receipt"] = normalized_receipt(data["receipt"])
    data["receipt"]["receipt_digest"] = source["receipt"]["receipt_digest"]
    data["validated_inputs"] = _sorted(
        tuple(normalized_validated_input(item) for item in data["validated_inputs"])
    )
    data["diagnostics"] = _sorted(data["diagnostics"])
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["provenance"]["input_digests"] = _sorted(data["provenance"]["input_digests"])
    data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
    data["uncertainty"]["sensitivity_notes"] = _sorted(data["uncertainty"]["sensitivity_notes"])
    return data


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return the canonical result envelope while retaining its final digest."""

    data = normalized_result_payload(value)
    data["result_digest"] = _dump(value)["result_digest"]
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "artifact_digest",
    "artifact_mapping_digest",
    "canonical_request_digest",
    "configuration_digest",
    "context_digest",
    "diagnostic_digest",
    "document_digest",
    "normalized_artifact",
    "normalized_diagnostic",
    "normalized_document",
    "normalized_lineage_result",
    "normalized_parser",
    "normalized_policy",
    "normalized_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_validated_input",
    "parser_digest",
    "policy_digest",
    "receipt_digest",
    "result_payload_digest",
    "validated_input_digest",
    "validated_inputs_digest",
]
