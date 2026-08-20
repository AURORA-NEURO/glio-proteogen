"""Small, provenance-first client for the public NCI Proteomic Data Commons API."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import md5, sha256
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from .public_proteomics.provenance import SourceReference

PDC_GRAPHQL_ENDPOINT = "https://pdc.cancer.gov/graphql"
PDC_STUDY_URL = "https://pdc.cancer.gov/pdc/study/{study_id}"
PDC_DOWNLOAD_HOSTS = frozenset({"pdc.cancer.gov", "d3iwtkuvwz4jtf.cloudfront.net"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
_MAX_CONTENT_VERIFY_BYTES = 2 * 1024 * 1024 * 1024
_MAX_DOWNLOAD_TIMEOUT_SECONDS = 300.0
_MZML_MEDIA_TYPES = frozenset(
    {"application/mzml", "application/xml", "text/xml", "application/octet-stream"}
)
_MZML_GZIP_MEDIA_TYPES = frozenset(
    {"application/gzip", "application/x-gzip", "application/octet-stream"}
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


class PdcError(RuntimeError):
    """Raised when the public API returns malformed or incomplete data."""


@dataclass(frozen=True, slots=True)
class PdcFile:
    study_id: str
    file_name: str
    file_type: str
    data_category: str
    file_format: str | None
    file_size: int
    md5: str | None
    location: str
    signed_url: str | None = None


@dataclass(frozen=True, slots=True)
class PdcStudySnapshot:
    study_id: str
    counts: tuple[tuple[str, str, int], ...]
    files: tuple[PdcFile, ...]
    source_url: str
    response_sha256: str


def _file_dict(value: PdcFile) -> dict[str, object]:
    return {
        "data_category": value.data_category,
        "file_format": value.file_format,
        "file_name": value.file_name,
        "file_size": value.file_size,
        "file_type": value.file_type,
        "location": value.location,
        "md5": value.md5,
        "signed_url": value.signed_url,
        "study_id": value.study_id,
    }


def _snapshot_dict(value: PdcStudySnapshot) -> dict[str, object]:
    return {
        "counts": [list(item) for item in value.counts],
        "files": [_file_dict(item) for item in value.files],
        "response_sha256": value.response_sha256,
        "source_url": value.source_url,
        "study_id": value.study_id,
    }


@dataclass(frozen=True, slots=True)
class PdcSourceReceipt:
    """Catalog-attested identity for one explicitly downloaded PDC file.

    The receipt binds the selected file declaration to the exact captured study
    response, caller-owned source bytes, and their observed hashes. It never
    performs network I/O and is intentionally research-only.
    """

    snapshot: PdcStudySnapshot
    file: PdcFile
    source_reference: SourceReference
    observed_sha256: str
    observed_md5: str
    observed_size: int
    observed_media_type: str = "application/mzml"

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, PdcStudySnapshot):
            raise TypeError("snapshot must be a PdcStudySnapshot")
        if not isinstance(self.file, PdcFile):
            raise TypeError("file must be a PdcFile")
        if not isinstance(self.source_reference, SourceReference):
            raise TypeError("source_reference must be a SourceReference")
        if self.file.study_id != self.snapshot.study_id:
            raise ValueError("PDC file study does not match the catalog snapshot")
        if self.file not in self.snapshot.files:
            raise ValueError("PDC file is absent from the captured catalog snapshot")
        if not _HEX64.fullmatch(self.snapshot.response_sha256):
            raise ValueError("PDC snapshot response hash is not a lowercase SHA-256")
        if not _HEX64.fullmatch(self.observed_sha256.removeprefix("sha256:")):
            raise ValueError("observed source hash is not a SHA-256")
        if not _HEX32.fullmatch(self.observed_md5.lower()):
            raise ValueError("observed source MD5 is malformed")
        if type(self.observed_size) is not int or self.observed_size < 0:
            raise ValueError("observed source size is invalid")
        observed_media = self.observed_media_type.split(";", 1)[0].strip().lower()
        try:
            allowed_media_types = _media_types(self.file.file_format)
        except PdcError as error:
            raise ValueError(
                "observed source media type is incompatible with the catalog mzML file"
            ) from error
        if observed_media not in allowed_media_types:
            raise ValueError(
                "observed source media type is incompatible with the catalog mzML file"
            )
        if self.file.file_format is None or self.file.file_format.lower() not in {
            "mzml",
            "mzml.gz",
        }:
            raise ValueError("PDC receipt file must declare mzML format")
        if self.source_reference.locator != self.file.location:
            raise ValueError("source reference locator does not match the catalog file")
        observed = self.observed_sha256
        if not observed.startswith("sha256:"):
            observed = "sha256:" + observed
        if self.source_reference.sha256 != observed:
            raise ValueError("source reference hash does not match observed bytes")
        if self.source_reference.byte_length != self.observed_size:
            raise ValueError("source reference size does not match observed bytes")
        if self.observed_size != self.file.file_size:
            raise ValueError("observed source size does not match the catalog file")
        if self.file.md5 is not None and self.observed_md5.lower() != self.file.md5.lower():
            raise ValueError("observed source MD5 does not match the catalog file")
        reference_media = _media_type(self.source_reference.media_type)
        if observed_media != reference_media and "application/octet-stream" not in {
            observed_media,
            reference_media,
        }:
            raise ValueError("observed source media type does not match the source reference")

    @property
    def response_sha256(self) -> str:
        return self.snapshot.response_sha256

    def as_dict(self) -> dict[str, object]:
        return {
            "file": _file_dict(self.file),
            "observed_md5": self.observed_md5.lower(),
            "observed_media_type": self.observed_media_type.split(";", 1)[0].strip().lower(),
            "observed_sha256": (
                self.observed_sha256
                if self.observed_sha256.startswith("sha256:")
                else "sha256:" + self.observed_sha256
            ),
            "observed_size": self.observed_size,
            "response_sha256": self.response_sha256,
            "snapshot": _snapshot_dict(self.snapshot),
            "source_reference": self.source_reference.as_dict(),
            "receipt_version": "pdc-source-receipt-1",
        }

    @property
    def digest(self) -> str:
        return sha256(
            json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def verify_pdc_source_content(
    receipt: PdcSourceReceipt,
    content: bytes | bytearray | BinaryIO,
    *,
    max_bytes: int = _MAX_CONTENT_VERIFY_BYTES,
) -> PdcSourceReceipt:
    """Recompute a receipt against caller-held source bytes.

    ``PdcSourceReceipt`` records hashes observed by the downloader, but callers
    may deserialize or construct a receipt separately from the bytes they hold.
    This bounded verifier closes that gap by checking the exact byte length,
    SHA-256, and catalog MD5 against the supplied content.  A binary stream is
    consumed once and is not rewound; no bytes are returned or persisted.
    """

    if not isinstance(receipt, PdcSourceReceipt):
        raise TypeError("receipt must be a PdcSourceReceipt")
    if type(max_bytes) is not int or not 0 < max_bytes <= _MAX_CONTENT_VERIFY_BYTES:
        raise ValueError("max_bytes is outside supported bounds")
    expected_size = receipt.observed_size
    if expected_size > max_bytes:
        raise PdcError("receipt exceeds the caller content verification limit")
    expected_sha256 = receipt.observed_sha256.removeprefix("sha256:")
    expected_md5 = receipt.observed_md5.lower()
    sha256_digest = sha256()
    md5_digest = md5(usedforsecurity=False)
    total = 0

    if isinstance(content, (bytes, bytearray)):
        chunks: Iterable[bytes] = (bytes(content),)
    else:
        chunks = ()
        while True:
            chunk = content.read(min(_DOWNLOAD_CHUNK_BYTES, max_bytes - total + 1))
            if not isinstance(chunk, (bytes, bytearray)):
                raise TypeError("content stream must return bytes")
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes or total > expected_size:
                raise PdcError("content exceeds the receipt byte length or caller limit")
            sha256_digest.update(chunk)
            md5_digest.update(chunk)

    if isinstance(content, (bytes, bytearray)):
        for chunk in chunks:
            total += len(chunk)
            if total > max_bytes or total > expected_size:
                raise PdcError("content exceeds the receipt byte length or caller limit")
            sha256_digest.update(chunk)
            md5_digest.update(chunk)
    if total != expected_size:
        raise PdcError("content length differs from the PDC receipt")
    if sha256_digest.hexdigest() != expected_sha256:
        raise PdcError("content SHA-256 differs from the PDC receipt")
    if md5_digest.hexdigest().lower() != expected_md5:
        raise PdcError("content MD5 differs from the PDC receipt")
    return receipt


def _post(query: str, *, timeout: float = 30.0) -> tuple[dict[str, Any], bytes]:
    body = json.dumps({"query": query}, separators=(",", ":")).encode("utf-8")
    request = Request(
        PDC_GRAPHQL_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS allowlist
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise PdcError("PDC response exceeds the bounded metadata limit")
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        raise PdcError("PDC returned non-JSON data") from error
    if not isinstance(decoded, dict) or decoded.get("errors"):
        raise PdcError("PDC returned a GraphQL error")
    data = decoded.get("data")
    if not isinstance(data, dict):
        raise PdcError("PDC response is missing data")
    return data, payload


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PdcError(f"PDC field {field} is not a non-empty string")
    return value


def _file(value: object) -> PdcFile:
    if not isinstance(value, dict):
        raise PdcError("PDC file entry is not an object")
    try:
        size = int(_string(value.get("file_size"), "file_size"))
    except ValueError as error:
        raise PdcError("PDC file size is not an integer") from error
    if size < 0:
        raise PdcError("PDC file size is negative")
    return PdcFile(
        study_id=_string(value.get("pdc_study_id"), "pdc_study_id"),
        file_name=_string(value.get("file_name"), "file_name"),
        file_type=_string(value.get("file_type"), "file_type"),
        data_category=_string(value.get("data_category"), "data_category"),
        file_format=value.get("file_format") if isinstance(value.get("file_format"), str) else None,
        file_size=size,
        md5=value.get("md5sum") if isinstance(value.get("md5sum"), str) else None,
        location=_string(value.get("file_location"), "file_location"),
        signed_url=(
            value.get("signedUrl", {}).get("url")
            if isinstance(value.get("signedUrl"), dict)
            and isinstance(value.get("signedUrl", {}).get("url"), str)
            else None
        ),
    )


def _approved_hosts(extra_hosts: Iterable[str]) -> frozenset[str]:
    hosts = set(PDC_DOWNLOAD_HOSTS)
    for host in extra_hosts:
        if (
            not isinstance(host, str)
            or not host
            or host != host.strip()
            or any(character.isspace() for character in host)
            or "/" in host
            or (":" in host and host != "::1")
        ):
            raise ValueError("approved download hosts must be exact host names")
        hosts.add(host.lower())
    return frozenset(hosts)


def _validate_download_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    host = parsed.hostname.lower() if parsed.hostname is not None else None
    try:
        port = parsed.port
    except ValueError as error:
        raise PdcError("PDC download URL has an invalid port") from error
    if (
        parsed.username is not None
        or parsed.password is not None
        or host is None
        or host not in allowed_hosts
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
    ):
        raise PdcError("PDC download URL is outside the exact host allowlist")
    if parsed.scheme == "https" and port not in {None, 443}:
        raise PdcError("PDC HTTPS download URL must use the default port")
    if parsed.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise PdcError("non-HTTPS PDC downloads are limited to loopback test hosts")


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(  # noqa: PLR0917
        self,
        request: Request,
        file: Any,  # noqa: ANN401
        code: int,
        msg: str,
        headers: Any,  # noqa: ANN401
        new_url: str,
    ) -> Request | None:
        target = urljoin(request.full_url, new_url)
        _validate_download_url(target, self._allowed_hosts)
        return super().redirect_request(request, file, code, msg, headers, target)


def _open_download_response(
    request: Request, *, timeout_seconds: float, allowed_hosts: frozenset[str]
) -> Any:  # noqa: ANN401
    opener = build_opener(_AllowlistedRedirectHandler(allowed_hosts))
    try:
        return opener.open(request, timeout=timeout_seconds)
    except PdcError:
        raise
    except HTTPError as error:
        raise PdcError(f"PDC download returned HTTP status {error.code}") from error
    except (OSError, URLError, TimeoutError) as error:
        raise PdcError("PDC download request failed") from error


def _media_types(file_format: str | None) -> frozenset[str]:
    if file_format is None:
        raise PdcError("PDC file has no declared mzML format")
    normalized = file_format.lower()
    if normalized == "mzml":
        return _MZML_MEDIA_TYPES
    if normalized == "mzml.gz":
        return _MZML_GZIP_MEDIA_TYPES
    raise PdcError("PDC raw retrieval supports only mzML or mzML.gz")


def _media_type(value: str | None) -> str:
    if value is None:
        raise PdcError("PDC download response has no Content-Type")
    media = value.split(";", 1)[0].strip().lower()
    if not media:
        raise PdcError("PDC download response has an empty Content-Type")
    return media


def _validate_response_headers(
    response: Any,  # noqa: ANN401
    file: PdcFile,
    source_reference: SourceReference | None,
) -> str:
    media_types = _media_types(file.file_format)
    response_media = _media_type(response.headers.get("Content-Type"))
    if response_media not in media_types:
        raise PdcError("PDC download Content-Type is incompatible with the declared mzML format")
    if source_reference is not None:
        reference_media = _media_type(source_reference.media_type)
        if reference_media not in media_types:
            raise PdcError(
                "source reference media type is incompatible with the declared mzML format"
            )
        if response_media != reference_media and "application/octet-stream" not in {
            response_media,
            reference_media,
        }:
            raise PdcError("PDC download Content-Type does not match the source reference")
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise PdcError("PDC download Content-Length is not an integer") from error
        if declared_length != file.file_size:
            raise PdcError("PDC download Content-Length differs from the file declaration")
    return response_media


class PdcClient:
    """Fetch bounded study metadata; never downloads raw spectra implicitly."""

    def study_snapshot(self, study_id: str, *, limit: int = 16) -> PdcStudySnapshot:
        if not study_id.startswith("PDC") or not study_id[3:].isdigit():
            raise ValueError("study_id must be a PDC accession")
        if not 1 <= limit <= 128:
            raise ValueError("limit must be between 1 and 128")
        query = (
            '{ filesCountPerStudy(pdc_study_id: "'
            + study_id
            + '") { pdc_study_id file_type files_count data_category } '
            'filesPerStudy(pdc_study_id: "'
            + study_id
            + f'", offset: 0, limit: {limit}) {{ pdc_study_id file_name file_type '
            "md5sum file_location file_size data_category file_format signedUrl { url } } }"
        )
        data, raw = _post(query)
        raw_counts = data.get("filesCountPerStudy")
        raw_files = data.get("filesPerStudy")
        if not isinstance(raw_counts, list) or not isinstance(raw_files, list):
            raise PdcError("PDC response is missing study collections")
        counts: list[tuple[str, str, int]] = []
        for item in raw_counts:
            if not isinstance(item, dict):
                raise PdcError("PDC count entry is not an object")
            try:
                count = int(str(item.get("files_count")))
            except (TypeError, ValueError) as error:
                raise PdcError("PDC file count is not an integer") from error
            if count < 0:
                raise PdcError("PDC file count is negative")
            counts.append(
                (
                    _string(item.get("data_category"), "data_category"),
                    _string(item.get("file_type"), "file_type"),
                    count,
                )
            )
        files = tuple(_file(item) for item in raw_files)
        if any(item.study_id != study_id for item in files):
            raise PdcError("PDC response file study does not match requested study")
        return PdcStudySnapshot(
            study_id=study_id,
            counts=tuple(sorted(counts)),
            files=tuple(sorted(files, key=lambda item: item.file_name)),
            source_url=PDC_STUDY_URL.format(study_id=study_id),
            response_sha256=sha256(raw).hexdigest(),
        )

    def download_file(
        self,
        file: PdcFile,
        destination: BinaryIO,
        *,
        max_bytes: int = 512 * 1024 * 1024,
        timeout_seconds: float = 120.0,
        approved_hosts: Iterable[str] = (),
    ) -> int:
        """Explicitly stream one signed PDC file into a caller-owned destination.

        Metadata discovery never calls this method. The signed URL must be HTTPS on
        an allowlisted PDC delivery host (or an exact caller-approved host), the
        declared size and response media must fit the caller's bound, and checksums
        supplied by PDC are checked before any verified bytes are copied to the
        destination. Redirects are revalidated at every hop.
        """
        total, _, _, _ = self._download_file(
            file,
            destination,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            approved_hosts=approved_hosts,
        )
        return total

    def download_file_with_receipt(
        self,
        file: PdcFile,
        snapshot: PdcStudySnapshot,
        source_reference: SourceReference,
        destination: BinaryIO,
        *,
        max_bytes: int = 512 * 1024 * 1024,
        timeout_seconds: float = 120.0,
        approved_hosts: Iterable[str] = (),
    ) -> PdcSourceReceipt:
        """Download one catalog-listed file and return its content-addressed receipt.

        This is the explicit raw-byte retrieval boundary. It never runs from a
        metadata query or the research inference pipeline, and it writes to the
        caller destination only after URL, media, size, SHA-256, and MD5 checks
        succeed.
        """

        if not isinstance(snapshot, PdcStudySnapshot):
            raise TypeError("snapshot must be a PdcStudySnapshot")
        if not isinstance(source_reference, SourceReference):
            raise TypeError("source_reference must be a SourceReference")
        if file not in snapshot.files:
            raise PdcError("PDC file is absent from the captured catalog snapshot")
        total, md5_hex, sha256_hex, observed_media_type = self._download_file(
            file,
            destination,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            approved_hosts=approved_hosts,
            source_reference=source_reference,
        )
        return PdcSourceReceipt(
            snapshot=snapshot,
            file=file,
            source_reference=source_reference,
            observed_sha256="sha256:" + sha256_hex,
            observed_md5=md5_hex,
            observed_size=total,
            observed_media_type=observed_media_type,
        )

    @staticmethod
    def _download_file(
        file: PdcFile,
        destination: BinaryIO,
        *,
        max_bytes: int,
        timeout_seconds: float,
        approved_hosts: Iterable[str],
        source_reference: SourceReference | None = None,
    ) -> tuple[int, str, str, str]:
        if type(max_bytes) is not int or not 0 < max_bytes <= 2 * 1024 * 1024 * 1024:
            raise ValueError("max_bytes is outside supported bounds")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= _MAX_DOWNLOAD_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds is outside supported bounds")
        if file.signed_url is None:
            raise PdcError("PDC file has no signed download URL")
        allowed_hosts = _approved_hosts(approved_hosts)
        _validate_download_url(file.signed_url, allowed_hosts)
        if file.file_size > max_bytes:
            raise PdcError("PDC file exceeds the caller download limit")
        request = Request(  # noqa: S310 - HTTPS host allowlist validated above
            file.signed_url,
            headers={"Accept": ", ".join(sorted(_media_types(file.file_format)))},
        )
        md5_digest = md5(usedforsecurity=False)
        sha256_digest = sha256()
        total = 0
        with _open_download_response(
            request,
            timeout_seconds=float(timeout_seconds),
            allowed_hosts=allowed_hosts,
        ) as response:
            response_media = _validate_response_headers(response, file, source_reference)
            with SpooledTemporaryFile(
                max_size=min(max_bytes, _SPOOL_MEMORY_BYTES), mode="w+b"
            ) as spool:
                while True:
                    try:
                        chunk = response.read(min(_DOWNLOAD_CHUNK_BYTES, max_bytes - total + 1))
                    except (OSError, TimeoutError) as error:
                        raise PdcError("PDC download request failed") from error
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes or total > file.file_size:
                        raise PdcError("PDC download exceeded the declared or caller limit")
                    md5_digest.update(chunk)
                    sha256_digest.update(chunk)
                    spool.write(chunk)
                if total != file.file_size:
                    raise PdcError("PDC download length differs from metadata")
                md5_hex = md5_digest.hexdigest().lower()
                sha256_hex = sha256_digest.hexdigest()
                if file.md5 is not None and md5_hex != file.md5.lower():
                    raise PdcError("PDC download MD5 differs from metadata")
                observed_sha = "sha256:" + sha256_hex
                if source_reference is not None and (
                    source_reference.byte_length != total or source_reference.sha256 != observed_sha
                ):
                    raise PdcError("PDC download bytes differ from the source reference")
                spool.seek(0)
                while chunk := spool.read(_DOWNLOAD_CHUNK_BYTES):
                    destination.write(chunk)
        return total, md5_hex, sha256_hex, response_media
