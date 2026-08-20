"""Content-addressed provenance helpers for non-governed research inputs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_MANIFEST_SOURCES: Final = 256


class ProvenanceError(ValueError):
    """Raised when a research provenance record is malformed."""


def canonical_json_bytes(value: object) -> bytes:
    """Return stable UTF-8 JSON bytes for a JSON-compatible value."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ProvenanceError("value is not canonical JSON compatible") from error
    return encoded.encode("utf-8")


def sha256_digest(value: bytes | str | object) -> str:
    """Digest bytes, text, or canonical JSON as a prefixed SHA-256 value."""

    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_json_bytes(value)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_digest(value: str) -> str:
    if not _DIGEST_RE.fullmatch(value):
        raise ProvenanceError("digest must be lowercase sha256:<64 hex characters>")
    return value


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Immutable reference to bytes or a bounded public response."""

    source_id: str
    locator: str
    media_type: str
    sha256: str
    byte_length: int
    retrieved_at: str
    license_or_terms: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.locator.strip():
            raise ProvenanceError("source id and locator are required")
        if not self.media_type.strip() or not self.license_or_terms.strip():
            raise ProvenanceError("media type and usage terms are required")
        _validate_digest(self.sha256)
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ProvenanceError("byte length must be a non-negative integer")
        if not self.retrieved_at.endswith("Z"):
            raise ProvenanceError("retrieved_at must be a UTC timestamp ending in Z")

    def as_dict(self) -> dict[str, object]:
        return {
            "byte_length": self.byte_length,
            "license_or_terms": self.license_or_terms,
            "locator": self.locator,
            "media_type": self.media_type,
            "retrieved_at": self.retrieved_at,
            "sha256": self.sha256,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """A deterministic manifest for source and derived research artifacts."""

    manifest_id: str
    created_at: str
    purpose: str
    sources: tuple[SourceReference, ...]
    derivation: str

    def __post_init__(self) -> None:
        if not self.manifest_id.strip() or not self.purpose.strip() or not self.derivation.strip():
            raise ProvenanceError("manifest identity, purpose, and derivation are required")
        if not self.created_at.endswith("Z"):
            raise ProvenanceError("created_at must be a UTC timestamp ending in Z")
        if not self.sources or len(self.sources) > MAX_MANIFEST_SOURCES:
            raise ProvenanceError("manifest source count is outside the bounded range")
        source_ids = tuple(source.source_id for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ProvenanceError("manifest source ids must be unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "derivation": self.derivation,
            "manifest_id": self.manifest_id,
            "purpose": self.purpose,
            "sources": [source.as_dict() for source in self.sources],
        }

    @property
    def digest(self) -> str:
        return sha256_digest(self.as_dict())


def verify_file_reference(path: Path, reference: SourceReference, *, max_bytes: int) -> None:
    """Verify one local file without reading beyond the configured cap."""

    if max_bytes < 0 or not path.is_file():
        raise ProvenanceError("source path is not a regular file")
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            length += len(chunk)
            if length > max_bytes:
                raise ProvenanceError("source exceeds the configured byte cap")
            digest.update(chunk)
    observed = "sha256:" + digest.hexdigest()
    if length != reference.byte_length or observed != reference.sha256:
        raise ProvenanceError("local source bytes do not match the provenance reference")
