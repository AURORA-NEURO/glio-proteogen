"""Canonical, bounded contracts for a source review without clinical promotion."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final

from glio_proteogen.kernel.models import FrozenModel

PROFILE_ID: Final = "cptac-gbm-clinical-gap-review/1.0.0"
SOURCE_SCHEMA: Final = "cptac-gbm-2024-clinical-table-s1/1.0.0"
REVIEW_SCHEMA: Final = "cptac-gbm-clinical-gap-review/1.0.0"
MAX_RECEIPT_BYTES: Final = 1_048_576


class ResolutionError(ValueError):
    """A sanitized source-review contract or binding failure."""


def canonical_bytes(value: object) -> bytes:
    """Encode finite JSON deterministically without echoing rejected content."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ResolutionError("review JSON cannot be encoded") from None


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_digest(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ResolutionError("review digest is invalid")
    return value


def _digest_field(value: object) -> str:
    if value not in ("source_receipt_digest", "receipt_digest"):
        raise ResolutionError("review seal field is invalid")
    return str(value)


def seal_document(document: dict[str, object], digest_field: str) -> dict[str, object]:
    """Seal a fully materialized typed document; replace an earlier placeholder."""
    field = _digest_field(digest_field)
    if type(document) is not dict or any(type(key) is not str for key in document):
        raise ResolutionError("review document is invalid")
    values = {key: value for key, value in document.items() if key != field}
    return {**values, field: digest(values)}


def checked_receipt_document[ReceiptT: FrozenModel](
    document: object,
    model_type: type[ReceiptT],
    *,
    digest_field: str,
) -> ReceiptT:
    """Require a self-sealed, complete, exactly typed aggregate document.

    A valid seal establishes byte binding, not source authority or clinical truth.
    Source admission and cross-document lineage bindings belong to the owner.
    """
    field = _digest_field(digest_field)
    if (
        type(document) is not dict
        or any(type(key) is not str for key in document)
        or not isinstance(model_type, type)
        or not issubclass(model_type, FrozenModel)
        or field not in model_type.model_fields
        or getattr(model_type, "SEAL_FIELD", None) != field
    ):
        raise ResolutionError("a typed review document is required")
    try:
        declared = validate_digest(document.get(field))
        if seal_document(document, field)[field] != declared:
            raise ResolutionError("review document seal does not match")  # noqa: TRY301 -- sanitized boundary
        encoded = canonical_bytes(document)
        if len(encoded) > MAX_RECEIPT_BYTES:
            raise ResolutionError("review document exceeds its byte bound")  # noqa: TRY301 -- sanitized boundary
        checked = model_type.model_validate_json(encoded)
        if canonical_bytes(checked.model_dump(mode="json")) != encoded:
            raise ResolutionError("review document is not exactly typed and complete")  # noqa: TRY301 -- sanitized boundary
    except ResolutionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError, RecursionError):
        raise ResolutionError("review document was not accepted") from None
    return checked


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ResolutionError("review JSON has duplicate keys")
        result[key] = value
    return result


def parse_receipt[ReceiptT: FrozenModel](
    payload: bytes,
    model_type: type[ReceiptT],
    *,
    digest_field: str,
) -> ReceiptT:
    """Read bounded private receipt bytes, rejecting duplicate keys and aliases."""
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_RECEIPT_BYTES:
        raise ResolutionError("review receipt byte bound or type is invalid")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ResolutionError("review receipt JSON is invalid") from None
    return checked_receipt_document(document, model_type, digest_field=digest_field)


__all__ = [
    "MAX_RECEIPT_BYTES",
    "PROFILE_ID",
    "REVIEW_SCHEMA",
    "SOURCE_SCHEMA",
    "ResolutionError",
    "canonical_bytes",
    "checked_receipt_document",
    "digest",
    "parse_receipt",
    "seal_document",
    "validate_digest",
]
