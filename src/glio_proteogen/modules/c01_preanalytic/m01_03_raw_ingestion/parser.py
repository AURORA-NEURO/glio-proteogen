"""Bounded, content-first parser registry for M01-03.

This module intentionally stops at structural ingestion. It computes content identity, detects a
small set of open formats, and emits metadata-only contract objects. It never retains source
bytes, rows, sequences, spectra, variants, identifiers from the file, or interpreted biology.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING, Final, Protocol

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from glio_proteogen.contracts.m01_03 import (
    Compression,
    DetectedRawFormat,
    DiagnosticAction,
    DiagnosticSeverity,
    ParseDiagnostic,
    RawFormat,
    RawInputDisposition,
    ValidatedRawInputDescriptor,
)
from glio_proteogen.contracts.m01_03.v1 import (
    M0103_MAX_DECODED_BYTES,
    M0103_MAX_DIAGNOSTICS_PER_SOURCE,
    M0103_MAX_SOURCE_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO
    from xml.etree.ElementTree import Element

    from glio_proteogen.kernel.models import Identifier, Sha256Digest

_GZIP_MAGIC: Final = b"\x1f\x8b"
_XML_FORBIDDEN: Final = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_VCF_VERSION: Final = re.compile(r"^##fileformat=VCFv(4\.[1-5])$")
_FASTA_SEQUENCE: Final = re.compile(r"^[A-Za-z*.-]+$")
_MZTAB_SECTIONS: Final = frozenset({"PRT", "PEP", "PSM", "SML"})
_MZTAB_HEADERS: Final = frozenset({"PRH", "PEH", "PSH", "SMH"})
_MZTAB_MIN_COLUMNS: Final = 3
_VCF_MIN_COLUMNS: Final = 8
_GFF3_COLUMNS: Final = 9
_LIMIT_RANGE_MESSAGE: Final = "ingestion limit is outside the supported range"
_REGISTRY_MESSAGE: Final = "parser registry formats must be nonempty and unique"
_SOURCE_TYPE_MESSAGE: Final = "raw source must be bytes or a binary stream"
_STREAM_TYPE_MESSAGE: Final = "raw source stream must return bytes"
_XML_MEDIA_TYPES: Final = {
    RawFormat.MZML: "application/vnd.hupo.mzml+xml",
    RawFormat.MZIDENTML: "application/vnd.hupo.mzidentml+xml",
}
_TEXT_MEDIA_TYPES: Final = {
    RawFormat.MZTAB_M: "text/tab-separated-values",
    RawFormat.FASTA: "text/x-fasta",
    RawFormat.VCF: "text/x-vcf",
    RawFormat.GFF3: "text/x-gff3",
}
_EXTENSION_FORMATS: Final = {
    ".mzml": RawFormat.MZML,
    ".mzid": RawFormat.MZIDENTML,
    ".mzidentml": RawFormat.MZIDENTML,
    ".mztab": RawFormat.MZTAB_M,
    ".fa": RawFormat.FASTA,
    ".faa": RawFormat.FASTA,
    ".fna": RawFormat.FASTA,
    ".fasta": RawFormat.FASTA,
    ".vcf": RawFormat.VCF,
    ".gff": RawFormat.GFF3,
    ".gff3": RawFormat.GFF3,
}


@dataclass(frozen=True, slots=True)
class IngestionLimits:
    """Independent ceilings applied before parsing and during decompression."""

    max_source_bytes: int = 64 * 1024 * 1024
    max_decoded_bytes: int = 128 * 1024 * 1024
    max_diagnostics: int = 32

    def __post_init__(self) -> None:
        if not 0 < self.max_source_bytes <= M0103_MAX_SOURCE_BYTES:
            raise ValueError(_LIMIT_RANGE_MESSAGE)
        if not 0 < self.max_decoded_bytes <= M0103_MAX_DECODED_BYTES:
            raise ValueError(_LIMIT_RANGE_MESSAGE)
        if not 0 < self.max_diagnostics <= M0103_MAX_DIAGNOSTICS_PER_SOURCE:
            raise ValueError(_LIMIT_RANGE_MESSAGE)


_DEFAULT_LIMITS: Final = IngestionLimits()


@dataclass(frozen=True, slots=True)
class StructuralParse:
    """Private safe facts returned by a registered structural parser."""

    version: str | None
    record_count: int


class StructuralParser(Protocol):
    """Small extension point for future bounded format profiles."""

    @property
    def format(self) -> RawFormat: ...

    @property
    def media_type(self) -> str: ...

    def detects(self, payload: bytes) -> bool: ...

    def parse(self, payload: bytes) -> StructuralParse: ...


@dataclass(frozen=True, slots=True)
class _Parser:
    format: RawFormat
    media_type: str
    detector: Callable[[bytes], bool]
    reader: Callable[[bytes], StructuralParse]

    def detects(self, payload: bytes) -> bool:
        return self.detector(payload)

    def parse(self, payload: bytes) -> StructuralParse:
        return self.reader(payload)


@dataclass(frozen=True, slots=True)
class ParserRegistry:
    parsers: tuple[StructuralParser, ...]

    def __post_init__(self) -> None:
        formats = [parser.format for parser in self.parsers]
        if not formats or len(formats) != len(set(formats)):
            raise ValueError(_REGISTRY_MESSAGE)

    def candidates(self, payload: bytes) -> tuple[StructuralParser, ...]:
        return tuple(parser for parser in self.parsers if parser.detects(payload))


class _StructuralError(ValueError):
    code: str = "malformed_content"


class _UnsupportedVersionError(_StructuralError):
    code = "unsupported_version"


class _ForbiddenXmlError(_StructuralError):
    code = "forbidden_xml_construct"


class _InvalidUtf8Error(_StructuralError):
    code = "invalid_utf8"


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _xml_root(payload: bytes) -> Element:
    if _XML_FORBIDDEN.search(payload):
        raise _ForbiddenXmlError
    try:
        return ElementTree.fromstring(payload)
    except DefusedXmlException as error:
        raise _ForbiddenXmlError from error
    except ElementTree.ParseError as error:
        raise _StructuralError from error


def _detect_xml_root(payload: bytes, expected: str) -> bool:
    if not payload.lstrip().startswith(b"<"):
        return False
    if _XML_FORBIDDEN.search(payload):
        return f"<{expected.lower()}".encode() in payload[:4096].lower()
    try:
        root = ElementTree.fromstring(payload)
    except (DefusedXmlException, ElementTree.ParseError):
        # A truncated but recognizable XML root still belongs to its typed parser.
        prefix = payload[:4096].lower()
        return f"<{expected.lower()}".encode() in prefix
    root_name = _local_name(root.tag)
    if expected == "mzML" and root_name == "indexedmzML":
        return any(_local_name(child.tag) == "mzML" for child in root)
    return root_name == expected


def _parse_xml(payload: bytes, raw_format: RawFormat) -> StructuralParse:
    root = _xml_root(payload)
    expected_root = "mzML" if raw_format is RawFormat.MZML else "MzIdentML"
    if raw_format is RawFormat.MZML and _local_name(root.tag) == "indexedmzML":
        root = next(
            (child for child in root if _local_name(child.tag) == "mzML"),
            root,
        )
    if _local_name(root.tag) != expected_root:
        raise _StructuralError
    version = root.attrib.get("version")
    if raw_format is RawFormat.MZML:
        if version not in {"1.1", "1.1.0"}:
            raise _UnsupportedVersionError
        required = "run"
        counted = {"spectrum", "chromatogram"}
    else:
        if version not in {"1.2", "1.2.0", "1.3", "1.3.0"}:
            raise _UnsupportedVersionError
        required = "DataCollection"
        counted = {"SpectrumIdentificationResult", "PeptideEvidence"}
    names = [_local_name(element.tag) for element in root.iter()]
    if required not in names:
        raise _StructuralError
    return StructuralParse(version=version, record_count=sum(name in counted for name in names))


def _decode_text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _InvalidUtf8Error from error


def _nonempty_lines(payload: bytes) -> list[str]:
    return [line for line in _decode_text(payload).splitlines() if line.strip()]


def _detect_mztab(payload: bytes) -> bool:
    try:
        lines = _nonempty_lines(payload)[:20]
        return any(line.startswith("MTD\tmzTab-version\t") for line in lines)
    except _InvalidUtf8Error:
        return False


def _parse_mztab(payload: bytes) -> StructuralParse:
    lines = _nonempty_lines(payload)
    version_lines = [line for line in lines if line.startswith("MTD\tmzTab-version\t")]
    if len(version_lines) != 1:
        raise _StructuralError
    fields = version_lines[0].split("\t")
    if len(fields) != _MZTAB_MIN_COLUMNS or fields[2] != "2.0.0-M":
        raise _UnsupportedVersionError
    headers: set[str] = set()
    records = 0
    for line in lines:
        fields = line.split("\t")
        if len(fields) < _MZTAB_MIN_COLUMNS:
            raise _StructuralError
        code = fields[0]
        if code in _MZTAB_HEADERS:
            headers.add(code)
        elif code in _MZTAB_SECTIONS:
            expected_header = {"PRT": "PRH", "PEP": "PEH", "PSM": "PSH", "SML": "SMH"}[code]
            if expected_header not in headers:
                raise _StructuralError
            records += 1
        elif code not in {"MTD", "COM"}:
            raise _StructuralError
    return StructuralParse(version="2.0.0-M", record_count=records)


def _detect_fasta(payload: bytes) -> bool:
    try:
        lines = _nonempty_lines(payload)
    except _InvalidUtf8Error:
        return False
    return bool(lines and lines[0].startswith(">"))


def _parse_fasta(payload: bytes) -> StructuralParse:
    lines = _nonempty_lines(payload)
    count = 0
    has_residues = False
    for line in lines:
        if line.startswith(">"):
            if len(line) == 1 or (count and not has_residues):
                raise _StructuralError
            count += 1
            has_residues = False
        else:
            if count == 0 or not _FASTA_SEQUENCE.fullmatch(line):
                raise _StructuralError
            has_residues = True
    if count == 0 or not has_residues:
        raise _StructuralError
    return StructuralParse(version=None, record_count=count)


def _detect_vcf(payload: bytes) -> bool:
    try:
        lines = _nonempty_lines(payload)
    except _InvalidUtf8Error:
        return False
    return bool(lines and lines[0].startswith("##fileformat=VCFv"))


def _parse_vcf(payload: bytes) -> StructuralParse:
    lines = _nonempty_lines(payload)
    match = _VCF_VERSION.fullmatch(lines[0]) if lines else None
    if match is None:
        if lines and lines[0].startswith("##fileformat=VCFv"):
            raise _UnsupportedVersionError
        raise _StructuralError
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("#CHROM\t")),
        -1,
    )
    if header_index < 0 or len(lines[header_index].split("\t")) < _VCF_MIN_COLUMNS:
        raise _StructuralError
    records = 0
    for line in lines[header_index + 1 :]:
        if line.startswith("#"):
            raise _StructuralError
        fields = line.split("\t")
        if len(fields) < _VCF_MIN_COLUMNS:
            raise _StructuralError
        try:
            position = int(fields[1])
        except ValueError as error:
            raise _StructuralError from error
        if position < 1 or not fields[3] or not fields[4]:
            raise _StructuralError
        records += 1
    return StructuralParse(version=match.group(1), record_count=records)


def _detect_gff3(payload: bytes) -> bool:
    try:
        lines = _nonempty_lines(payload)
    except _InvalidUtf8Error:
        return False
    return bool(lines and lines[0].startswith("##gff-version"))


def _parse_gff3(payload: bytes) -> StructuralParse:
    lines = _nonempty_lines(payload)
    if not lines or lines[0] != "##gff-version 3":
        if lines and lines[0].startswith("##gff-version"):
            raise _UnsupportedVersionError
        raise _StructuralError
    records = 0
    for line in lines[1:]:
        if line == "##FASTA":
            break
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != _GFF3_COLUMNS:
            raise _StructuralError
        try:
            start, end = int(fields[3]), int(fields[4])
        except ValueError as error:
            raise _StructuralError from error
        if start < 1 or end < start or fields[6] not in {"+", "-", ".", "?"}:
            raise _StructuralError
        if fields[7] not in {"0", "1", "2", "."}:
            raise _StructuralError
        records += 1
    return StructuralParse(version="3", record_count=records)


DEFAULT_REGISTRY: Final = ParserRegistry(
    parsers=(
        _Parser(
            RawFormat.MZML,
            _XML_MEDIA_TYPES[RawFormat.MZML],
            lambda payload: _detect_xml_root(payload, "mzML"),
            lambda payload: _parse_xml(payload, RawFormat.MZML),
        ),
        _Parser(
            RawFormat.MZIDENTML,
            _XML_MEDIA_TYPES[RawFormat.MZIDENTML],
            lambda payload: _detect_xml_root(payload, "MzIdentML"),
            lambda payload: _parse_xml(payload, RawFormat.MZIDENTML),
        ),
        _Parser(
            RawFormat.MZTAB_M,
            _TEXT_MEDIA_TYPES[RawFormat.MZTAB_M],
            _detect_mztab,
            _parse_mztab,
        ),
        _Parser(RawFormat.FASTA, _TEXT_MEDIA_TYPES[RawFormat.FASTA], _detect_fasta, _parse_fasta),
        _Parser(RawFormat.VCF, _TEXT_MEDIA_TYPES[RawFormat.VCF], _detect_vcf, _parse_vcf),
        _Parser(RawFormat.GFF3, _TEXT_MEDIA_TYPES[RawFormat.GFF3], _detect_gff3, _parse_gff3),
    )
)


def _read_bounded(source: bytes | BinaryIO, limit: int) -> tuple[bytes, bool]:
    if isinstance(source, bytes | bytearray | memoryview):
        payload = bytes(source)
        return payload[: limit + 1], len(payload) > limit
    if not hasattr(source, "read"):
        raise TypeError(_SOURCE_TYPE_MESSAGE)
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = source.read(min(64 * 1024, remaining))
        if not isinstance(chunk, bytes):
            raise TypeError(_STREAM_TYPE_MESSAGE)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    return payload, len(payload) > limit


def _decode_gzip(payload: bytes, limit: int) -> tuple[bytes | None, str | None]:
    decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        decoded = decompressor.decompress(payload, limit + 1)
        if len(decoded) > limit or decompressor.unconsumed_tail:
            return None, "decompressed_size_limit_exceeded"
        decoded += decompressor.flush(limit + 1 - len(decoded))
    except zlib.error:
        return None, "invalid_gzip"
    if len(decoded) > limit:
        return None, "decompressed_size_limit_exceeded"
    if not decompressor.eof or decompressor.unused_data:
        return None, "invalid_gzip"
    return decoded, None


def _expected_digest(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.casefold()
    if not normalized.startswith("sha256:"):
        normalized = f"sha256:{normalized}"
    return normalized if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized) else "invalid"


def _diagnostic(
    source_id: str,
    code: str,
    action: DiagnosticAction,
    *,
    ordinal: int = 1,
) -> ParseDiagnostic:
    severity = (
        DiagnosticSeverity.CRITICAL
        if action is DiagnosticAction.REJECT
        else DiagnosticSeverity.ERROR
        if action in {DiagnosticAction.QUARANTINE, DiagnosticAction.HUMAN_REVIEW}
        else DiagnosticSeverity.WARNING
    )
    identifier_hash = hashlib.sha256(f"{source_id}|{code}|{ordinal}".encode()).hexdigest()[:24]
    messages: dict[str, str] = {
        "checksum_mismatch": "The supplied content checksum did not match the expected digest.",
        "raw_size_limit_exceeded": "The raw source exceeded the configured byte limit.",
        "decompressed_size_limit_exceeded": "Decoded content exceeded the configured byte limit.",
        "invalid_gzip": (
            "The gzip container is malformed, truncated, concatenated, or has trailing data."
        ),
        "unsupported_format": "Content did not match any supported raw-input profile.",
        "ambiguous_format": "Content matched more than one supported raw-input profile.",
        "extension_content_mismatch": (
            "The advisory filename extension disagrees with content detection."
        ),
        "malformed_content": "Content failed the selected format's structural validation.",
        "unsupported_version": "The detected format version is outside the supported profile.",
        "forbidden_xml_construct": "XML contains a forbidden document type or entity declaration.",
        "invalid_utf8": "Textual content is not valid UTF-8.",
    }
    return ParseDiagnostic(
        diagnostic_id=f"diagnostic.m0103.{identifier_hash}",
        code=code,
        severity=severity,
        action=action,
        message=messages[code],
    )


def _failed_descriptor(  # noqa: PLR0913 - explicit contract fields make failure construction safe.
    *,
    source_id: Identifier,
    digest: Sha256Digest,
    raw_size: int,
    decoded_size: int,
    checksum_verified: bool,
    code: str,
    action: DiagnosticAction,
) -> ValidatedRawInputDescriptor:
    return ValidatedRawInputDescriptor(
        source_id=source_id,
        source_digest=digest,
        source_size_bytes=min(raw_size, M0103_MAX_SOURCE_BYTES),
        decoded_size_bytes=min(decoded_size, M0103_MAX_DECODED_BYTES),
        detected=None,
        record_count=0,
        checksum_verified=checksum_verified,
        structural_validation_passed=False,
        disposition=(
            RawInputDisposition.REJECTED
            if action is DiagnosticAction.REJECT
            else RawInputDisposition.QUARANTINED
        ),
        diagnostics=(_diagnostic(source_id, code, action),),
    )


def _advisory_format(filename: str | None) -> tuple[RawFormat | None, bool]:
    if filename is None:
        return None, False
    name = PurePath(filename).name.casefold()
    gzip_suffix = name.endswith(".gz")
    if gzip_suffix:
        name = name[:-3]
    return _EXTENSION_FORMATS.get(PurePath(name).suffix), gzip_suffix


def parse_raw_input(  # noqa: PLR0911, PLR0913 - typed fail-fast outcomes are the public API.
    source: bytes | BinaryIO,
    *,
    source_id: Identifier,
    filename: str | None = None,
    expected_sha256: str | None = None,
    limits: IngestionLimits = _DEFAULT_LIMITS,
    registry: ParserRegistry = DEFAULT_REGISTRY,
) -> ValidatedRawInputDescriptor:
    """Validate one bounded source and return metadata only.

    Filename extensions are advisory. The exact supplied-byte digest is computed before
    decompression. Blocking outcomes are typed descriptors rather than parser exceptions.
    """

    raw, exceeded = _read_bounded(source, limits.max_source_bytes)
    raw_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if exceeded:
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=0,
            checksum_verified=False,
            code="raw_size_limit_exceeded",
            action=DiagnosticAction.REJECT,
        )
    expected = _expected_digest(expected_sha256)
    checksum_verified = expected is None or expected == raw_digest
    if not checksum_verified:
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=0,
            checksum_verified=False,
            code="checksum_mismatch",
            action=DiagnosticAction.REJECT,
        )
    compression = Compression.GZIP if raw.startswith(_GZIP_MAGIC) else Compression.NONE
    payload = raw
    if compression is Compression.GZIP:
        decoded, failure = _decode_gzip(raw, limits.max_decoded_bytes)
        if failure is not None or decoded is None:
            return _failed_descriptor(
                source_id=source_id,
                digest=raw_digest,
                raw_size=len(raw),
                decoded_size=(
                    limits.max_decoded_bytes
                    if failure == "decompressed_size_limit_exceeded"
                    else 0
                ),
                checksum_verified=True,
                code=failure or "invalid_gzip",
                action=(
                    DiagnosticAction.REJECT
                    if failure == "decompressed_size_limit_exceeded"
                    else DiagnosticAction.QUARANTINE
                ),
            )
        payload = decoded
    elif len(payload) > limits.max_decoded_bytes:
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=limits.max_decoded_bytes,
            checksum_verified=True,
            code="decompressed_size_limit_exceeded",
            action=DiagnosticAction.REJECT,
        )
    candidates = registry.candidates(payload)
    if not candidates:
        code = "invalid_utf8" if _looks_textual_but_invalid_utf8(payload) else "unsupported_format"
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=len(payload),
            checksum_verified=True,
            code=code,
            action=DiagnosticAction.QUARANTINE,
        )
    if len(candidates) > 1:
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=len(payload),
            checksum_verified=True,
            code="ambiguous_format",
            action=DiagnosticAction.QUARANTINE,
        )
    parser = candidates[0]
    try:
        structural = parser.parse(payload)
    except _StructuralError as error:
        return _failed_descriptor(
            source_id=source_id,
            digest=raw_digest,
            raw_size=len(raw),
            decoded_size=len(payload),
            checksum_verified=True,
            code=error.code,
            action=DiagnosticAction.QUARANTINE,
        )
    diagnostics: tuple[ParseDiagnostic, ...] = ()
    advisory_format, advisory_gzip = _advisory_format(filename)
    if (advisory_format is not None and advisory_format is not parser.format) or (
        filename is not None and advisory_gzip is not (compression is Compression.GZIP)
    ):
        diagnostics = (
            _diagnostic(
                source_id,
                "extension_content_mismatch",
                DiagnosticAction.RECORD,
            ),
        )
    return ValidatedRawInputDescriptor(
        source_id=source_id,
        source_digest=raw_digest,
        source_size_bytes=len(raw),
        decoded_size_bytes=len(payload),
        detected=DetectedRawFormat(
            format=parser.format,
            version=structural.version,
            compression=compression,
            media_type=parser.media_type,
        ),
        record_count=structural.record_count,
        checksum_verified=True,
        structural_validation_passed=True,
        disposition=RawInputDisposition.ACCEPTED,
        diagnostics=diagnostics[: limits.max_diagnostics],
    )


def _looks_textual_but_invalid_utf8(payload: bytes) -> bool:
    if b"\x00" in payload:
        return False
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


__all__ = [
    "DEFAULT_REGISTRY",
    "IngestionLimits",
    "ParserRegistry",
    "StructuralParse",
    "StructuralParser",
    "parse_raw_input",
]
