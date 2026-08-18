"""Adversarial tests for explicit, bounded PDC raw-byte retrieval."""

from __future__ import annotations

import hashlib
import io
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.research.pdc import PdcClient, PdcError, PdcFile, PdcStudySnapshot
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
    assert receipt.source_reference.sha256 == sha256_digest(payload)


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
