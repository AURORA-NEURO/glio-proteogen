"""Small, provenance-first client for the public NCI Proteomic Data Commons API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import md5, sha256
from typing import Any, BinaryIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PDC_GRAPHQL_ENDPOINT = "https://pdc.cancer.gov/graphql"
PDC_STUDY_URL = "https://pdc.cancer.gov/pdc/study/{study_id}"
PDC_DOWNLOAD_HOSTS = frozenset({"pdc.cancer.gov", "d3iwtkuvwz4jtf.cloudfront.net"})


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
    ) -> int:
        """Explicitly stream one signed PDC file into a caller-owned destination.

        Metadata discovery never calls this method. The signed URL must be HTTPS on
        an allowlisted PDC delivery host, the declared size must fit the caller's
        bound, and an MD5 supplied by PDC is checked over the received bytes before
        returning.
        """
        if not 0 < max_bytes <= 2 * 1024 * 1024 * 1024:
            raise ValueError("max_bytes is outside supported bounds")
        if file.signed_url is None:
            raise PdcError("PDC file has no signed download URL")
        parsed = urlparse(file.signed_url)
        if parsed.scheme != "https" or parsed.hostname not in PDC_DOWNLOAD_HOSTS:
            raise PdcError("PDC signed URL is outside the HTTPS delivery-host allowlist")
        if file.file_size > max_bytes:
            raise PdcError("PDC file exceeds the caller download limit")
        request = Request(  # noqa: S310 - HTTPS host allowlist validated above
            file.signed_url, headers={"Accept": "application/octet-stream"}
        )
        digest = md5(usedforsecurity=False)
        total = 0
        with urlopen(request, timeout=120.0) as response:  # noqa: S310 - HTTPS allowlist above
            while True:
                chunk = response.read(min(1024 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes or total > file.file_size:
                    raise PdcError("PDC download exceeded the declared or caller limit")
                digest.update(chunk)
                destination.write(chunk)
        if total != file.file_size:
            raise PdcError("PDC download length differs from metadata")
        if file.md5 is not None and digest.hexdigest().lower() != file.md5.lower():
            raise PdcError("PDC download MD5 differs from metadata")
        return total
