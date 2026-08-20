"""Adversarial tests for explicit, bounded PDC raw-byte retrieval."""

from __future__ import annotations

import hashlib
import io
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, Self

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.research import pdc as pdc_module
from glio_proteogen.research.pdc import (
    PdcClient,
    PdcError,
    PdcFile,
    PdcSourceReceipt,
    PdcStudySnapshot,
    verify_pdc_source_content,
)
from glio_proteogen.research.public_proteomics.provenance import SourceReference, sha256_digest


@dataclass(frozen=True, slots=True)
class _Route:
    status: int
    body: bytes
    content_type: str
    content_length: int | None = None
    location: str | None = None
    delay_seconds: float = 0.0


class _Handler(BaseHTTPRequestHandler):
    routes: ClassVar[Mapping[str, _Route]] = {}

    def do_GET(self) -> None:
        route = self.routes.get(self.path)
        if route is None:
            self.send_error(404)
            return
        if route.delay_seconds:
            time.sleep(route.delay_seconds)
        self.send_response(route.status)
        self.send_header("Content-Type", route.content_type)
        length = route.content_length if route.content_length is not None else len(route.body)
        self.send_header("Content-Length", str(length))
        if route.location is not None:
            self.send_header("Location", route.location)
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(route.body)

    def log_message(self, _format: str, *_args: object) -> None:
        return None


class _MemoryResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.headers = {
            "Content-Type": "application/mzml",
            "Content-Length": str(len(payload)),
        }
        self._read = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self.payload


@contextmanager
def _http_server(routes: Mapping[str, _Route]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.routes = routes
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        _Handler.routes = {}


def _file(url: str, payload: bytes, *, md5: bytes | None = None) -> PdcFile:
    expected = payload if md5 is None else md5
    return PdcFile(
        study_id="PDC000204",
        file_name="fixture.mzML",
        file_type="Mass",
        data_category="Raw",
        file_format="mzML",
        file_size=len(expected),
        md5=hashlib.md5(expected, usedforsecurity=False).hexdigest(),
        location=url,
        signed_url=url,
    )


def _snapshot_and_reference(
    file: PdcFile, payload: bytes
) -> tuple[PdcStudySnapshot, SourceReference]:
    snapshot = PdcStudySnapshot(
        study_id=file.study_id,
        counts=((file.data_category, file.file_type, 1),),
        files=(file,),
        source_url="https://pdc.cancer.gov/pdc/study/PDC000204",
        response_sha256="a" * 64,
    )
    reference = SourceReference(
        source_id="pdc:PDC000204:fixture",
        locator=file.location,
        media_type="application/mzml",
        sha256=sha256_digest(payload),
        byte_length=len(payload),
        retrieved_at="2026-08-18T00:00:00Z",
        license_or_terms="public metadata-bound research fixture",
    )
    return snapshot, reference


def test_successful_retrieval_is_receipt_bound_and_commits_only_verified_bytes() -> None:
    payload = b"<mzML>verified</mzML>"
    with _http_server({"/ok": _Route(200, payload, "application/mzml")}) as base:
        file = _file(f"{base}/ok", payload)
        snapshot, reference = _snapshot_and_reference(file, payload)
        destination = io.BytesIO()
        receipt = PdcClient().download_file_with_receipt(
            file,
            snapshot,
            reference,
            destination,
            approved_hosts=("127.0.0.1",),
            timeout_seconds=2,
        )
    assert destination.getvalue() == payload
    assert receipt.observed_size == len(payload)
    assert receipt.observed_media_type == "application/mzml"
    assert receipt.as_dict()["observed_media_type"] == "application/mzml"
    assert receipt.source_reference.sha256 == sha256_digest(payload)
    assert verify_pdc_source_content(receipt, payload) is receipt
    assert verify_pdc_source_content(receipt, io.BytesIO(payload)) is receipt


def test_source_content_verifier_rejects_hash_length_and_limit_tampering() -> None:
    payload = b"<mzML>verified-content</mzML>"
    file = _file("memory://PDC000204/content", payload)
    snapshot, reference = _snapshot_and_reference(file, payload)
    receipt = PdcSourceReceipt(
        snapshot=snapshot,
        file=file,
        source_reference=reference,
        observed_sha256=reference.sha256,
        observed_md5=file.md5 or "",
        observed_size=len(payload),
    )
    with pytest.raises(PdcError, match="SHA-256"):
        verify_pdc_source_content(receipt, b"<mzML>tampered-content</mzML>")
    with pytest.raises(PdcError, match="length"):
        verify_pdc_source_content(receipt, payload[:-1])
    with pytest.raises(PdcError, match="limit"):
        verify_pdc_source_content(receipt, payload, max_bytes=len(payload) - 1)
    with pytest.raises(ValueError, match="max_bytes"):
        verify_pdc_source_content(receipt, payload, max_bytes=0)
    with pytest.raises(TypeError, match="bytes"):
        verify_pdc_source_content(receipt, io.StringIO("not bytes"))  # type: ignore[arg-type]


def test_pdc_file_rejects_boolean_size_metadata() -> None:
    payload = b"<mzML>verified</mzML>"
    file = _file("memory://PDC000204/content", payload)
    with pytest.raises(ValueError, match="file_size"):
        replace(file, file_size=True)  # type: ignore[arg-type]


def test_receipt_rejects_tampered_observed_media_type() -> None:
    payload = b"<mzML>verified</mzML>"
    with _http_server({"/ok": _Route(200, payload, "application/mzML; charset=binary")}) as base:
        file = _file(f"{base}/ok", payload)
        snapshot, reference = _snapshot_and_reference(file, payload)
        receipt = PdcClient().download_file_with_receipt(
            file,
            snapshot,
            reference,
            io.BytesIO(),
            approved_hosts=("127.0.0.1",),
            timeout_seconds=2,
        )
    with pytest.raises(ValueError, match="media type"):
        replace(receipt, observed_media_type="text/plain")


def test_redirect_to_unapproved_host_is_rejected_before_following() -> None:
    payload = b"<mzML>blocked</mzML>"
    with _http_server(
        {
            "/redirect": _Route(
                302,
                b"",
                "application/mzml",
                content_length=0,
                location="https://evil.example/secret.mzML",
            )
        }
    ) as base:
        file = _file(f"{base}/redirect", payload)
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="allowlist"):
            PdcClient().download_file(
                file, destination, approved_hosts=("127.0.0.1",), timeout_seconds=2
            )
        assert destination.getvalue() == b""


def test_download_enforces_declared_size_and_caller_cap() -> None:
    payload = b"<mzML>bounded</mzML>"
    with _http_server({"/large": _Route(200, payload, "application/mzml")}) as base:
        file = _file(f"{base}/large", payload)
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="caller download limit"):
            PdcClient().download_file(
                file,
                destination,
                max_bytes=len(payload) - 1,
                approved_hosts=("127.0.0.1",),
            )
        assert destination.getvalue() == b""

        truncated_metadata = _file(f"{base}/large", payload)
        with pytest.raises(PdcError, match="Content-Length"):
            PdcClient().download_file(
                truncated_metadata.__class__(
                    truncated_metadata.study_id,
                    truncated_metadata.file_name,
                    truncated_metadata.file_type,
                    truncated_metadata.data_category,
                    truncated_metadata.file_format,
                    len(payload) + 1,
                    truncated_metadata.md5,
                    truncated_metadata.location,
                    truncated_metadata.signed_url,
                ),
                io.BytesIO(),
                approved_hosts=("127.0.0.1",),
            )


def test_checksum_mismatch_never_reaches_destination() -> None:
    expected = b"<mzML>expected</mzML>"
    observed = b"<mzML>tampered</mzML>"
    assert len(expected) == len(observed)
    with _http_server({"/checksum": _Route(200, observed, "application/mzml")}) as base:
        file = _file(f"{base}/checksum", expected)
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="MD5"):
            PdcClient().download_file(
                file, destination, approved_hosts=("127.0.0.1",), timeout_seconds=2
            )
        assert destination.getvalue() == b""


def test_media_type_mismatch_is_rejected() -> None:
    payload = b"<mzML>media</mzML>"
    with _http_server({"/media": _Route(200, payload, "text/plain")}) as base:
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="Content-Type"):
            PdcClient().download_file(
                _file(f"{base}/media", payload),
                destination,
                approved_hosts=("127.0.0.1",),
            )
        assert destination.getvalue() == b""


def test_truncated_response_is_rejected_without_partial_write() -> None:
    payload = b"<mzML>truncated</mzML>"
    with _http_server(
        {"/truncated": _Route(200, payload[:-1], "application/mzml", len(payload))}
    ) as base:
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="length"):
            PdcClient().download_file(
                _file(f"{base}/truncated", payload),
                destination,
                approved_hosts=("127.0.0.1",),
                timeout_seconds=2,
            )
        assert destination.getvalue() == b""


def test_timeout_is_bounded_and_does_not_write_partial_bytes() -> None:
    payload = b"<mzML>delayed</mzML>"
    with _http_server(
        {"/slow": _Route(200, payload, "application/mzml", delay_seconds=0.2)}
    ) as base:
        destination = io.BytesIO()
        with pytest.raises(PdcError, match="download request failed"):
            PdcClient().download_file(
                _file(f"{base}/slow", payload),
                destination,
                approved_hosts=("127.0.0.1",),
                timeout_seconds=0.05,
            )
        assert destination.getvalue() == b""


@pytest.mark.parametrize("host", ["", " pdc.cancer.gov", "pdc.cancer.gov/", "pdc:443"])
def test_caller_approved_hosts_are_exact_and_not_authority_fragments(host: str) -> None:
    with pytest.raises(ValueError, match="exact host"):
        pdc_module._approved_hosts((host,))


@pytest.mark.parametrize(
    "url",
    [
        "ftp://pdc.cancer.gov/file",
        "http://pdc.cancer.gov/file",
        "https://pdc.cancer.gov:444/file",
        "https://user@pdc.cancer.gov/file",
        "https://pdc.cancer.gov/file#fragment",
        "https://unapproved.example/file",
        "https://pdc.cancer.gov:bad/file",
    ],
)
def test_download_url_validation_rejects_transport_and_authority_escalation(url: str) -> None:
    with pytest.raises(PdcError):
        pdc_module._validate_download_url(url, frozenset(pdc_module.PDC_DOWNLOAD_HOSTS))


@pytest.mark.parametrize("file_format", [None, "fasta"])
def test_raw_retrieval_rejects_unsupported_file_formats(file_format: str | None) -> None:
    with pytest.raises(PdcError, match="mzML"):
        pdc_module._media_types(file_format)
    with pytest.raises(PdcError, match="Content-Type"):
        pdc_module._media_type(None)
    with pytest.raises(PdcError, match="Content-Type"):
        pdc_module._media_type(" ; charset=utf-8")


def test_gzipped_mzml_declares_gzip_media_types() -> None:
    assert "application/gzip" in pdc_module._media_types("mzml.gz")


def test_response_header_validation_binds_media_and_declared_length() -> None:
    payload = b"<mzML>headers</mzML>"
    file = _file("https://pdc.cancer.gov/files/headers", payload)
    good = SimpleNamespace(
        headers={
            "Content-Type": "application/mzml; charset=utf-8",
            "Content-Length": str(len(payload)),
        }
    )
    pdc_module._validate_response_headers(good, file, None)
    cases = (
        ({"Content-Type": "text/plain", "Content-Length": str(len(payload))}, None),
        ({"Content-Type": "application/mzml", "Content-Length": "bad"}, None),
        ({"Content-Type": "application/mzml", "Content-Length": str(len(payload) + 1)}, None),
    )
    for headers, reference in cases:
        with pytest.raises(PdcError):
            pdc_module._validate_response_headers(SimpleNamespace(headers=headers), file, reference)


def test_retrieval_rejects_reference_media_and_timeout_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"<mzML>reference</mzML>"
    file = _file("https://pdc.cancer.gov/files/reference", payload)
    snapshot, reference = _snapshot_and_reference(file, payload)
    bad_reference = SourceReference(
        reference.source_id,
        reference.locator,
        "text/plain",
        reference.sha256,
        reference.byte_length,
        reference.retrieved_at,
        reference.license_or_terms,
    )
    with pytest.raises(ValueError, match="timeout"):
        PdcClient().download_file(file, io.BytesIO(), timeout_seconds=0)
    monkeypatch.setattr(
        pdc_module,
        "_open_download_response",
        lambda *_args, **_kwargs: _MemoryResponse(payload),
    )
    with pytest.raises(PdcError, match="source reference media"):
        PdcClient().download_file_with_receipt(file, snapshot, bad_reference, io.BytesIO())


def test_read_failure_and_over_limit_are_safe_before_destination_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"<mzML>failure</mzML>"
    file = _file("https://pdc.cancer.gov/files/failure", payload)

    class _ReadFailure(_MemoryResponse):
        def read(self, _limit: int) -> bytes:
            raise OSError

    monkeypatch.setattr(
        pdc_module,
        "_open_download_response",
        lambda *_args, **_kwargs: _ReadFailure(payload),
    )
    with pytest.raises(PdcError, match="request failed"):
        PdcClient().download_file(file, io.BytesIO())

    class _OverLimit(_MemoryResponse):
        def __init__(self) -> None:
            super().__init__(payload[:1])
            self.headers["Content-Length"] = str(len(payload))

        def read(self, _limit: int) -> bytes:
            return payload + b"!"

    monkeypatch.setattr(
        pdc_module,
        "_open_download_response",
        lambda *_args, **_kwargs: _OverLimit(),
    )
    with pytest.raises(PdcError, match="exceeded"):
        PdcClient().download_file(file, io.BytesIO())
