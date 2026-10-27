"""Common limits and canonical bindings for source-only RNA admission."""

from __future__ import annotations

import hashlib
import json
import re

PROFILE_ID = "cptac-gbm-native-star-purity-preflight/1.0.0"
MAX_CASES = 256
MAX_CONTEXT_RECORDS = 16_384
MAX_CONTEXT_SOURCES = 256
MAX_CONTEXT_BYTES = 32 * 1_024 * 1_024
MAX_METADATA_BYTES = 8 * 1_024 * 1_024
MAX_OUTPUT_BYTES = 8 * 1_024 * 1_024


class AdmissionError(ValueError):
    """Sanitized admission failure; messages never include source rows or IDs."""


def canonical_bytes(value: object) -> bytes:
    """Canonical JSON without a trailing newline; reject non-JSON numeric values."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise AdmissionError("admission metadata cannot be canonically encoded") from None


def digest(value: object) -> str:
    """Bind a complete canonical document without interpreting its provenance."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_digest(value: object) -> str:
    """Require one exact SHA-256 digest; it is not an issuer authentication."""
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise AdmissionError("admission digest is invalid")
    return value


def require(condition: bool, message: str) -> None:  # noqa: FBT001 -- assertion primitive
    """Raise one sanitized invariant failure at an explicit trust boundary."""
    if not condition:
        raise AdmissionError(message)


__all__ = [
    "MAX_CASES",
    "MAX_CONTEXT_BYTES",
    "MAX_CONTEXT_RECORDS",
    "MAX_CONTEXT_SOURCES",
    "MAX_METADATA_BYTES",
    "MAX_OUTPUT_BYTES",
    "PROFILE_ID",
    "AdmissionError",
    "canonical_bytes",
    "digest",
    "require",
    "validate_digest",
]
