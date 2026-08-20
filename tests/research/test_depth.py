from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

import pytest

from glio_proteogen.research.public_proteomics import (
    FormatError,
    PDCClientConfig,
    PDCError,
    PDCMetadataClient,
    ProvenanceError,
    SourceManifest,
    SourceReference,
    aggregate_evidence,
    canonical_json_bytes,
    extract_fasta_structure,
    extract_mzidentml_structure,
    extract_mzml_structure,
    sha256_digest,
    verify_file_reference,
)
from glio_proteogen.research.public_proteomics.formats import MAX_LOCAL_BYTES

if TYPE_CHECKING:
    from collections.abc import Callable

_ROOT = Path(__file__).parents[2]
_FIXTURE = _ROOT / "research" / "fixtures" / "pdc" / "pdc000204.metadata.json"
_PDC_CONFIG = PDCClientConfig(timeout_seconds=2.0, max_response_bytes=4096, user_agent="test/deep")


def _transport(
    response: bytes, *, status: int = 200, content_type: str = "application/json"
) -> Callable[[str, bytes, float, str, int], tuple[int, bytes, str]]:
    def call(
        _url: str, _payload: bytes, _timeout: float, _user_agent: str, _max_bytes: int
    ) -> tuple[int, bytes, str]:
        return status, response, content_type

    return call


def test_pdc_config_rejects_each_invalid_bound() -> None:
    with pytest.raises(PDCError, match="timeout"):
        PDCClientConfig(timeout_seconds=0.0)
    with pytest.raises(PDCError, match="timeout"):
        PDCClientConfig(timeout_seconds=61.0)
    with pytest.raises(PDCError, match="response cap"):
        PDCClientConfig(max_response_bytes=0)
    with pytest.raises(PDCError, match="user agent"):
        PDCClientConfig(user_agent="  ")


def test_pdc_metadata_rejects_missing_text_and_bad_counts() -> None:
    record = json.loads(_FIXTURE.read_text(encoding="utf-8"))["data"]["study"][0]
    missing = dict(record)
    del missing["study_name"]
    with pytest.raises(PDCError, match="study_name"):
        PDCMetadataClient._parse_response({"data": {"study": [missing]}}, "PDC000204")
    bad_count = dict(record)
    bad_count["cases_count"] = True
    with pytest.raises(PDCError, match="cases_count"):
        PDCMetadataClient._parse_response({"data": {"study": [bad_count]}}, "PDC000204")
    with pytest.raises(PDCError, match="object"):
        PDCMetadataClient._parse_response({"data": {"study": [None]}}, "PDC000204")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"[]", "object"),
        (b'{"data":null}', "data"),
        (b'{"data":{"study":[]}}', "not unique"),
        (b'{"data":{"study":[{},{}]}}', "not unique"),
        (b"not-json", "UTF-8 JSON"),
    ],
)
def test_pdc_fetch_rejects_malformed_response(payload: bytes, message: str) -> None:
    client = PDCMetadataClient(_PDC_CONFIG, _transport(payload))
    with pytest.raises(PDCError, match=message):
        client.fetch("PDC000204", retrieved_at="2026-08-17T00:00:00Z")


def test_pdc_fetch_rejects_http_status_content_type_and_size() -> None:
    with pytest.raises(PDCError, match="status"):
        PDCMetadataClient(_PDC_CONFIG, _transport(b"{}", status=503)).fetch(
            "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
        )
    with pytest.raises(PDCError, match="JSON"):
        PDCMetadataClient(_PDC_CONFIG, _transport(b"{}", content_type="text/plain")).fetch(
            "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
        )
    tiny = PDCClientConfig(timeout_seconds=2.0, max_response_bytes=1, user_agent="test/deep")
    assert tiny.max_response_bytes == 1
    _client = PDCMetadataClient(tiny, _transport(b"123456"))
    with pytest.raises(PDCError, match="exceeds"):
        _client.fetch("PDC000204")


def test_default_pdc_transport_is_bounded_and_translates_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = _FIXTURE.read_bytes()

    class Response:
        status: ClassVar[int] = 200
        headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}

        def __init__(self) -> None:
            self._served = False

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            if self._served:
                return b""
            self._served = True
            assert limit == _PDC_CONFIG.max_response_bytes + 1
            return response_body

    def urlopen(_request: urllib.request.Request, *, timeout: float) -> Response:
        assert timeout == _PDC_CONFIG.timeout_seconds
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    snapshot = PDCMetadataClient(_PDC_CONFIG).fetch(
        "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
    )
    assert snapshot.response_bytes == len(response_body)

    def failing_urlopen(_request: urllib.request.Request, *, timeout: float) -> Response:
        del timeout
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)
    with pytest.raises(PDCError, match="request failed"):
        PDCMetadataClient(_PDC_CONFIG).fetch("PDC000204")


def test_default_pdc_transport_drains_short_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = _FIXTURE.read_bytes()

    class ShortReadResponse:
        status: ClassVar[int] = 200
        headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}

        def __init__(self) -> None:
            self._offset = 0
            self.read_calls = 0

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            self.read_calls += 1
            assert limit > 0
            chunk = response_body[self._offset : self._offset + min(limit, 7)]
            self._offset += len(chunk)
            return chunk

    response = ShortReadResponse()

    def urlopen(_request: urllib.request.Request, *, timeout: float) -> ShortReadResponse:
        assert timeout == _PDC_CONFIG.timeout_seconds
        return response

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    snapshot = PDCMetadataClient(_PDC_CONFIG).fetch(
        "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
    )
    assert response.read_calls > 1
    assert response._offset == len(response_body)
    assert snapshot.response_bytes == len(response_body)
    assert snapshot.response_sha256 == sha256_digest(response_body)


def test_provenance_rejects_non_json_and_invalid_references(tmp_path: Path) -> None:
    with pytest.raises(ProvenanceError, match="canonical"):
        canonical_json_bytes(float("nan"))
    with pytest.raises(ProvenanceError, match="digest"):
        SourceReference("bad", "memory:bad", "text/plain", "sha256:bad", 0, "nowZ", "test")
    with pytest.raises(ProvenanceError, match="negative"):
        SourceReference("bad", "memory:bad", "text/plain", sha256_digest(b""), -1, "nowZ", "test")
    with pytest.raises(ProvenanceError, match="required"):
        SourceReference(" ", "memory:bad", "text/plain", sha256_digest(b""), 0, "nowZ", "test")
    with pytest.raises(ProvenanceError, match="source count"):
        SourceManifest("m", "nowZ", "purpose", (), "derivation")
    payload = b"expected"
    path = tmp_path / "x"
    path.write_bytes(b"other")
    reference = SourceReference(
        "x", str(path), "text/plain", sha256_digest(payload), len(payload), "nowZ", "test"
    )
    with pytest.raises(ProvenanceError, match="match"):
        verify_file_reference(path, reference, max_bytes=100)
    with pytest.raises(ProvenanceError, match="regular"):
        verify_file_reference(tmp_path / "missing", reference, max_bytes=100)


def test_formats_cover_invalid_xml_levels_empty_fasta_and_size() -> None:
    with pytest.raises(FormatError):
        extract_mzml_structure(b"<mzML>")
    with pytest.raises(FormatError):
        extract_mzml_structure(b"<mzML><cvParam name='ms level' value='x'/></mzML>")
    with pytest.raises(FormatError):
        extract_mzml_structure(b"<mzML><cvParam name='ms level' value='0'/></mzML>")
    with pytest.raises(FormatError):
        extract_fasta_structure(b">\nMPEP\n")
    with pytest.raises(FormatError):
        extract_fasta_structure(b">empty\n>next\nMPEP\n")
    with pytest.raises(FormatError):
        extract_fasta_structure(b"\xff")
    with pytest.raises(FormatError):
        extract_fasta_structure(b"A" * (MAX_LOCAL_BYTES + 1))
    summary = extract_mzidentml_structure(
        b"<MzIdentML><SpectrumIdentificationItem passThreshold='false'/></MzIdentML>"
    )
    assert summary.pass_threshold_item_count == 0


def test_formats_count_multiple_ms_levels_and_element_limit() -> None:
    data = (
        b"<mzML>"
        + b"<cvParam name='ms level' value='1'/><cvParam name='ms level' value='2'/>"
        + b"</mzML>"
    )
    assert extract_mzml_structure(data).ms_level_counts == ((1, 1), (2, 1))
    too_many = b"<mzML>" + b"<x/>" * 200_001 + b"</mzML>"
    with pytest.raises(FormatError, match="element"):
        extract_mzml_structure(too_many)


def test_aggregate_rejects_unbound_and_mismatched_sources() -> None:
    response = _FIXTURE.read_bytes()
    snapshot = PDCMetadataClient(transport=_transport(response)).fetch(
        "PDC000204", retrieved_at="2026-08-17T00:00:00Z"
    )
    fasta = b">x\nMPEP\n"
    summary = extract_fasta_structure(fasta)
    manifest = SourceManifest(
        "m",
        "2026-08-17T00:00:00Z",
        "purpose",
        (snapshot.source_reference,),
        "derivation",
    )
    with pytest.raises(ValueError, match="not in the manifest"):
        aggregate_evidence(manifest, snapshot, {"local": summary})
    local_ref = SourceReference(
        "local",
        "memory:local",
        "text/plain",
        sha256_digest(fasta),
        len(fasta),
        "2026-08-17T00:00:00Z",
        "test",
    )
    complete = SourceManifest(
        "m2",
        "2026-08-17T00:00:00Z",
        "purpose",
        (snapshot.source_reference, local_ref),
        "derivation",
    )
    with pytest.raises(ValueError, match="does not match"):
        aggregate_evidence(
            complete, snapshot, {"local": extract_fasta_structure(b">x\nMPEPTIDE\n")}
        )
    bad_pdc_ref = SourceReference(
        snapshot.source_reference.source_id,
        snapshot.source_reference.locator,
        snapshot.source_reference.media_type,
        sha256_digest(b"different"),
        9,
        snapshot.source_reference.retrieved_at,
        snapshot.source_reference.license_or_terms,
    )
    bad_manifest = SourceManifest(
        "m3",
        "2026-08-17T00:00:00Z",
        "purpose",
        (bad_pdc_ref,),
        "derivation",
    )
    with pytest.raises(ValueError, match="exactly"):
        aggregate_evidence(bad_manifest, snapshot, {})
