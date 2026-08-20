from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from glio_proteogen.research.public_proteomics import (
    ProvenanceError,
    SourceManifest,
    SourceReference,
    canonical_json_bytes,
    sha256_digest,
    verify_file_reference,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_canonical_digest_is_order_independent() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert sha256_digest({"b": 2, "a": 1}) == sha256_digest({"a": 1, "b": 2})


def test_manifest_rejects_duplicate_sources_and_bad_timestamps() -> None:
    source = SourceReference(
        "one",
        "memory:one",
        "text/plain",
        sha256_digest(b"x"),
        1,
        "2026-08-17T00:00:00Z",
        "test",
    )
    with pytest.raises(ProvenanceError, match="unique"):
        SourceManifest("m", "2026-08-17T00:00:00Z", "test", (source, source), "test")
    with pytest.raises(ProvenanceError, match="timestamp"):
        SourceReference(
            "two", "memory:two", "text/plain", sha256_digest(b"x"), 1, "2026-08-17", "test"
        )


@pytest.mark.parametrize("length", [True, 1.0])
def test_source_reference_rejects_non_integer_byte_lengths(length: object) -> None:
    with pytest.raises(ProvenanceError, match="non-negative integer"):
        SourceReference(
            "source",
            "memory:source",
            "text/plain",
            sha256_digest(b"x"),
            length,  # type: ignore[arg-type]
            "2026-08-17T00:00:00Z",
            "terms",
        )


def test_file_reference_is_content_and_length_checked(tmp_path: Path) -> None:
    payload = b"bounded local evidence\n"
    path = tmp_path / "fixture.txt"
    path.write_bytes(payload)
    reference = SourceReference(
        "fixture",
        str(path),
        "text/plain",
        sha256_digest(payload),
        len(payload),
        "2026-08-17T00:00:00Z",
        "test fixture",
    )
    verify_file_reference(path, reference, max_bytes=1024)
    with pytest.raises(ProvenanceError, match="cap"):
        verify_file_reference(path, reference, max_bytes=2)
