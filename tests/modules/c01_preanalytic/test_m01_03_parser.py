"""Focused behavior tests for the bounded M01-03 parser registry."""

from __future__ import annotations

import gzip
import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from glio_proteogen.contracts.m01_03 import (
    Compression,
    DiagnosticAction,
    RawFormat,
    RawInputDisposition,
    ValidatedRawInputDescriptor,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    parse_raw_input,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "m01_03"


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _codes(result: ValidatedRawInputDescriptor) -> tuple[str, ...]:
    return tuple(diagnostic.code for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    ("filename", "raw_format", "version", "records"),
    [
        ("mzml.valid.mzML", RawFormat.MZML, "1.1.0", 1),
        ("mzidentml.valid.mzid", RawFormat.MZIDENTML, "1.3.0", 2),
        ("mztab_m.valid.mzTab", RawFormat.MZTAB_M, "2.0.0-M", 4),
        ("proteins.valid.fasta", RawFormat.FASTA, None, 2),
        ("variants.valid.vcf", RawFormat.VCF, "4.5", 1),
        ("annotations.valid.gff3", RawFormat.GFF3, "3", 2),
    ],
)
def test_supported_format_is_detected_from_content(
    filename: str,
    raw_format: RawFormat,
    version: str | None,
    records: int,
) -> None:
    payload = _fixture(filename)

    result = parse_raw_input(payload, source_id="source.valid", filename=filename)

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.detected is not None
    assert result.detected.format is raw_format
    assert result.detected.version == version
    assert result.detected.compression is Compression.NONE
    assert result.record_count == records
    assert result.source_size_bytes == len(payload)
    assert result.decoded_size_bytes == len(payload)
    assert result.diagnostics == ()


def test_gzip_is_detected_by_magic_and_checksum_covers_supplied_bytes() -> None:
    payload = _fixture("proteins.valid.fasta.gz")
    expected_digest = hashlib.sha256(payload).hexdigest().upper()

    result = parse_raw_input(
        payload,
        source_id="source.gzip",
        filename=None,
        expected_sha256=expected_digest,
    )

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.detected is not None
    assert result.detected.format is RawFormat.FASTA
    assert result.detected.compression is Compression.GZIP
    assert result.source_digest == f"sha256:{expected_digest.casefold()}"
    assert result.decoded_size_bytes == len(_fixture("proteins.valid.fasta"))


def test_checksum_mismatch_is_a_typed_rejection() -> None:
    result = parse_raw_input(
        _fixture("proteins.valid.fasta"),
        source_id="source.checksum",
        expected_sha256="0" * 64,
    )

    assert result.disposition is RawInputDisposition.REJECTED
    assert result.checksum_verified is False
    assert result.detected is None
    assert _codes(result) == ("checksum_mismatch",)
    assert result.diagnostics[0].action is DiagnosticAction.REJECT


def test_forbidden_xml_construct_has_its_own_typed_diagnostic() -> None:
    result = parse_raw_input(
        _fixture("mzml.doctype.invalid.mzML"),
        source_id="source.forbidden-xml",
    )

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert result.detected is None
    assert _codes(result) == ("forbidden_xml_construct",)
    assert result.diagnostics[0].action is DiagnosticAction.QUARANTINE


def test_gff3_fasta_tail_is_not_parsed_as_feature_rows() -> None:
    payload = (
        b"##gff-version 3\n"
        b"chr1\ttest\tgene\t1\t4\t.\t+\t.\tID=gene1\n"
        b"##FASTA\n"
        b">chr1\n"
        b"ACGT\n"
    )

    result = parse_raw_input(payload, source_id="source.gff-fasta")

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.detected is not None
    assert result.detected.format is RawFormat.GFF3
    assert result.record_count == 1


def test_source_at_exact_raw_cap_is_accepted() -> None:
    payload = _fixture("proteins.valid.fasta")
    limits = IngestionLimits(
        max_source_bytes=len(payload),
        max_decoded_bytes=len(payload),
        max_diagnostics=4,
    )

    result = parse_raw_input(payload, source_id="source.raw-exact", limits=limits)

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.source_size_bytes == limits.max_source_bytes


def test_source_one_byte_over_raw_cap_is_rejected() -> None:
    payload = _fixture("proteins.valid.fasta")
    limits = IngestionLimits(
        max_source_bytes=len(payload) - 1,
        max_decoded_bytes=len(payload),
        max_diagnostics=4,
    )

    result = parse_raw_input(payload, source_id="source.raw-over", limits=limits)

    assert result.disposition is RawInputDisposition.REJECTED
    assert _codes(result) == ("raw_size_limit_exceeded",)
    assert result.source_size_bytes == limits.max_source_bytes + 1


def test_gzip_payload_at_exact_decoded_cap_is_accepted() -> None:
    decoded = _fixture("proteins.valid.fasta")
    payload = gzip.compress(decoded, mtime=0)
    limits = IngestionLimits(
        max_source_bytes=len(payload),
        max_decoded_bytes=len(decoded),
        max_diagnostics=4,
    )

    result = parse_raw_input(payload, source_id="source.decoded-exact", limits=limits)

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.decoded_size_bytes == limits.max_decoded_bytes


def test_gzip_payload_one_byte_over_decoded_cap_is_rejected() -> None:
    decoded = _fixture("proteins.valid.fasta")
    payload = gzip.compress(decoded, mtime=0)
    limits = IngestionLimits(
        max_source_bytes=len(payload),
        max_decoded_bytes=len(decoded) - 1,
        max_diagnostics=4,
    )

    result = parse_raw_input(payload, source_id="source.decoded-over", limits=limits)

    assert result.disposition is RawInputDisposition.REJECTED
    assert _codes(result) == ("decompressed_size_limit_exceeded",)
    assert result.decoded_size_bytes == limits.max_decoded_bytes


def test_extension_is_advisory_and_mismatch_is_recorded() -> None:
    result = parse_raw_input(
        _fixture("proteins.valid.fasta"),
        source_id="source.extension",
        filename="synthetic.vcf",
    )

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.detected is not None
    assert result.detected.format is RawFormat.FASTA
    assert _codes(result) == ("extension_content_mismatch",)
    assert result.diagnostics[0].action is DiagnosticAction.RECORD


def test_truncated_recognizable_xml_is_malformed_not_unknown() -> None:
    result = parse_raw_input(
        _fixture("mzml.truncated.invalid.mzML"),
        source_id="source.malformed",
    )

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("malformed_content",)


def test_recognized_unsupported_version_is_quarantined() -> None:
    result = parse_raw_input(
        _fixture("mzml.unsupported.invalid.mzML"),
        source_id="source.unsupported-version",
    )

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("unsupported_version",)


def test_bytes_and_binary_streams_produce_identical_descriptors() -> None:
    payload = _fixture("variants.valid.vcf")

    from_bytes = parse_raw_input(payload, source_id="source.equivalent", filename="input.vcf")
    from_stream = parse_raw_input(
        BytesIO(payload),
        source_id="source.equivalent",
        filename="input.vcf",
    )

    assert from_stream == from_bytes


def test_raw_values_do_not_leak_into_diagnostics_or_output() -> None:
    raw_value = "RAW-PRIVATE-MARKER-9b80f7"
    payload = f">synthetic\nACGT\n{raw_value} contains spaces\n".encode()

    result = parse_raw_input(payload, source_id="source.redaction")
    serialized = result.model_dump_json()

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("malformed_content",)
    assert raw_value not in serialized
    assert "contains spaces" not in serialized


def test_invalid_gzip_is_quarantined_without_guessing_format() -> None:
    result = parse_raw_input(
        _fixture("gzip.truncated.invalid.gz"),
        source_id="source.bad-gzip",
    )

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert result.detected is None
    assert _codes(result) == ("invalid_gzip",)


def test_unknown_content_is_quarantined() -> None:
    result = parse_raw_input(
        _fixture("unknown.invalid.bin"),
        source_id="source.unknown",
    )

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("unsupported_format",)


def test_invalid_utf8_text_is_typed_without_echoing_bytes() -> None:
    payload = b"synthetic-text-\xff-private-marker"

    result = parse_raw_input(payload, source_id="source.invalid-utf8")

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("invalid_utf8",)
    assert "private-marker" not in result.model_dump_json()


@pytest.mark.parametrize(
    "payload",
    [
        gzip.compress(b">one\nACGT\n", mtime=0) + b"trailing",
        gzip.compress(b">one\nACGT\n", mtime=0) + gzip.compress(b">two\nTGCA\n", mtime=0),
    ],
)
def test_gzip_trailing_or_concatenated_members_are_quarantined(payload: bytes) -> None:
    result = parse_raw_input(payload, source_id="source.gzip-framing")

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert _codes(result) == ("invalid_gzip",)
