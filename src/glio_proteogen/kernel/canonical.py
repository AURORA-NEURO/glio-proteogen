"""Deterministic JSON and content hashing for contracts and audit events."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from glio_proteogen.kernel.models import Sha256Digest


def _json_ready(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_ready(value.model_dump(mode="python", by_alias=True, exclude_none=False))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        normalized = value.isoformat(timespec="microseconds")
        return normalized.replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON forbids NaN and infinity")
        return value
    if isinstance(value, Mapping):
        return _json_ready_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _json_ready_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    if not all(isinstance(key, str) for key in value):
        raise TypeError("canonical JSON object keys must be strings")
    return {key: _json_ready(item) for key, item in value.items()}


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a supported value deterministically without lossy coercion."""

    return json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_digest(value: Any) -> Sha256Digest:
    """Return a namespaced SHA-256 digest for the canonical representation."""

    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"sha256:{digest}"
