"""Compact branch-focused qualification for M01-03 public boundaries."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, cast

import pytest

from glio_proteogen.contracts.m01_03 import (
    Compression,
    RawFormat,
    RawInputDisposition,
)
from glio_proteogen.kernel.models import ControlRole
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    M0103Plugin,
    M0103Service,
    ParserRegistry,
    RawIngestionAuthorizationError,
    RawIngestionInputError,
    RawIngestionInputErrorCode,
    RawIngestionSubmission,
    StructuralParse,
    parse_raw_input,
    preflight_raw_ingestion_authorization,
)
from tests.modules.c01_preanalytic import test_m01_03_service as service_fixtures


@dataclass(frozen=True, slots=True)
class _StubParser:
    format: RawFormat
    media_type: str = "application/x-synthetic"
    detected: bool = True

    def detects(self, _payload: bytes) -> bool:
        return self.detected

    def parse(self, _payload: bytes) -> StructuralParse:
        return StructuralParse(version=None, record_count=0)


@pytest.mark.parametrize(
    "limits",
    [
        {"max_source_bytes": 0},
        {"max_decoded_bytes": 0},
        {"max_diagnostics": 0},
    ],
)
def test_ingestion_limits_reject_nonpositive_ceiling(limits: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="outside the supported range"):
        IngestionLimits(**limits)


def test_registry_requires_nonempty_unique_formats() -> None:
    with pytest.raises(ValueError, match="nonempty and unique"):
        ParserRegistry(())
    parser = _StubParser(RawFormat.FASTA)
    with pytest.raises(ValueError, match="nonempty and unique"):
        ParserRegistry((parser, parser))


def test_multiple_content_matches_are_quarantined_as_ambiguous() -> None:
    registry = ParserRegistry(
        (_StubParser(RawFormat.FASTA), _StubParser(RawFormat.VCF))
    )

    result = parse_raw_input(b"synthetic", source_id="source.ambiguous", registry=registry)

    assert result.disposition is RawInputDisposition.QUARANTINED
    assert result.diagnostics[0].code == "ambiguous_format"


@pytest.mark.parametrize("source", [bytearray(b">one\nACGT\n"), memoryview(b">one\nACGT\n")])
def test_bytes_like_sources_are_supported(source: object) -> None:
    result = parse_raw_input(cast("BinaryIO", source), source_id="source.bytes-like")

    assert result.disposition is RawInputDisposition.ACCEPTED


class _TextStream:
    def read(self, _size: int = -1) -> str:
        return "not bytes"


def test_parser_rejects_non_source_and_text_stream_types() -> None:
    with pytest.raises(TypeError, match="bytes or a binary stream"):
        parse_raw_input(cast("BinaryIO", object()), source_id="source.object")
    with pytest.raises(TypeError, match="stream must return bytes"):
        parse_raw_input(cast("BinaryIO", _TextStream()), source_id="source.text-stream")


def test_uncompressed_payload_obeys_decoded_limit() -> None:
    payload = b">one\nACGT\n"
    limits = IngestionLimits(
        max_source_bytes=len(payload),
        max_decoded_bytes=len(payload) - 1,
        max_diagnostics=2,
    )

    result = parse_raw_input(payload, source_id="source.decoded", limits=limits)

    assert result.disposition is RawInputDisposition.REJECTED
    assert result.diagnostics[0].code == "decompressed_size_limit_exceeded"


def test_checksum_prefix_and_invalid_checksum_text_are_handled() -> None:
    payload = b">one\nACGT\n"
    accepted = parse_raw_input(
        payload,
        source_id="source.prefixed",
        expected_sha256=service_fixtures._digest(payload),
    )
    rejected = parse_raw_input(
        payload,
        source_id="source.invalid-digest",
        expected_sha256="not-a-digest",
    )

    assert accepted.disposition is RawInputDisposition.ACCEPTED
    assert rejected.diagnostics[0].code == "checksum_mismatch"


def test_gzip_suffix_is_advisory_for_uncompressed_content() -> None:
    result = parse_raw_input(
        b">one\nACGT\n",
        source_id="source.suffix",
        filename="input.fasta.gz",
    )

    assert result.disposition is RawInputDisposition.ACCEPTED
    assert result.diagnostics[0].code == "extension_content_mismatch"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'<MzIdentML version="1.1"><DataCollection/></MzIdentML>', "unsupported_version"),
        (b'<MzIdentML version="1.3.0"><SequenceCollection/></MzIdentML>', "malformed_content"),
        (
            b'<indexedmzML><mzML version="1.1.0"><run><spectrum/></run></mzML></indexedmzML>',
            "accepted",
        ),
        (b"MTD\tmzTab-version\t1.0.0\n", "unsupported_version"),
        (
            b"MTD\tmzTab-version\t2.0.0-M\nMTD\tmzTab-version\t2.0.0-M\n",
            "malformed_content",
        ),
        (b"MTD\tmzTab-version\t2.0.0-M\nPSM\tone\ttwo\n", "malformed_content"),
        (b"MTD\tmzTab-version\t2.0.0-M\nBOGUS\tone\ttwo\n", "malformed_content"),
        (b">\nACGT\n", "malformed_content"),
        (b">one\n>two\nACGT\n", "malformed_content"),
        (b">one\nAC GT\n", "malformed_content"),
        (b">one\nACGT\n>two\n", "malformed_content"),
        (
            b"##fileformat=VCFv5.0\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n",
            "unsupported_version",
        ),
        (b"##fileformat=VCFv4.5\n", "malformed_content"),
        (
            b"##fileformat=VCFv4.5\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n#late\n",
            "malformed_content",
        ),
        (
            b"##fileformat=VCFv4.5\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\tbad\t.\tA\tT\t.\t.\t.\n",
            "malformed_content",
        ),
        (
            b"##fileformat=VCFv4.5\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\t0\t.\tA\tT\t.\t.\t.\n",
            "malformed_content",
        ),
        (b"##gff-version 2\n", "unsupported_version"),
        (b"##gff-version 3\nchr1\tbad\n", "malformed_content"),
        (b"##gff-version 3\nchr1\ts\tgene\tbad\t2\t.\t+\t.\tID=x\n", "malformed_content"),
        (b"##gff-version 3\nchr1\ts\tgene\t2\t1\t.\t+\t.\tID=x\n", "malformed_content"),
        (b"##gff-version 3\nchr1\ts\tgene\t1\t2\t.\t+\t9\tID=x\n", "malformed_content"),
        (b"binary\x00\xff", "unsupported_format"),
    ],
)
def test_structural_edge_is_typed(payload: bytes, code: str) -> None:
    result = parse_raw_input(payload, source_id="source.structural")

    if code == "accepted":
        assert result.disposition is RawInputDisposition.ACCEPTED
        assert result.record_count == 1
    else:
        assert result.disposition is RawInputDisposition.QUARANTINED
        assert result.diagnostics[0].code == code


@pytest.mark.parametrize(
    ("role", "state"),
    [
        (ControlRole.CONSENT, "revoked"),
        (ControlRole.IDENTITY_LINEAGE, "unresolved"),
        (ControlRole.APPROVED_CONFIGURATION, "rejected"),
        (ControlRole.PROVENANCE, "rejected"),
        (ControlRole.QUALITY, "unknown"),
        (ControlRole.SUPPORT, "rejected"),
        (ControlRole.INTENDED_USE, "unknown"),
    ],
)
def test_each_explicit_upstream_denial_fails_preflight(role: ControlRole, state: str) -> None:
    payload = service_fixtures._fixture("proteins.valid.fasta")
    request = service_fixtures._request(service_fixtures._source("authorization", payload))
    untrusted = request.model_dump(mode="python")
    untrusted["context"]["references"][role.value]["state"] = state

    with pytest.raises(RawIngestionAuthorizationError) as caught:
        preflight_raw_ingestion_authorization(untrusted)

    assert caught.value.role is role


def test_preflight_without_references_defers_to_contract_validation() -> None:
    preflight_raw_ingestion_authorization({})


@pytest.mark.parametrize("filename", ["", "x" * 1025, "bad\ud800name"])
def test_service_rejects_invalid_filename_hints(filename: str) -> None:
    payload = service_fixtures._fixture("proteins.valid.fasta")
    source = service_fixtures._source("filename", payload)

    with pytest.raises(RawIngestionInputError) as caught:
        M0103Service().execute(
            service_fixtures._request(source),
            {source.source_id: payload},
            {source.source_id: filename},
        )

    assert caught.value.code is RawIngestionInputErrorCode.INVALID_FILENAME


def test_service_rejects_invalid_source_and_accepts_binary_stream() -> None:
    payload = service_fixtures._fixture("proteins.valid.fasta")
    source = service_fixtures._source("stream", payload)
    request = service_fixtures._request(source)
    with pytest.raises(RawIngestionInputError) as caught:
        M0103Service().execute(
            request,
            {source.source_id: cast("BinaryIO", object())},
        )
    assert caught.value.code is RawIngestionInputErrorCode.INVALID_SOURCE

    result = M0103Service().execute(request, {source.source_id: BytesIO(payload)})
    assert result.disposition is RawInputDisposition.ACCEPTED


def test_compression_policy_and_declaration_mismatches_quarantine() -> None:
    decoded = service_fixtures._fixture("proteins.valid.fasta")
    payload = gzip.compress(decoded, mtime=0)
    policy = service_fixtures._policy()
    policy = policy.model_copy(update={"allowed_compressions": (Compression.NONE,)})
    source = service_fixtures._source(
        "gzip",
        payload,
        compression=None,
    )
    request = service_fixtures._request(source, policy=policy)
    result = M0103Service().execute(request, {source.source_id: payload})
    assert result.raw_inputs[0].diagnostics[0].code == "detected_compression_disabled"

    declared = service_fixtures._source("declared-gzip", payload, compression=Compression.NONE)
    mismatch = M0103Service().execute(
        service_fixtures._request(declared),
        {declared.source_id: payload},
    )
    assert "declared_compression_mismatch" in {
        diagnostic.code for diagnostic in mismatch.raw_inputs[0].diagnostics
    }


def test_rejected_parser_diagnostic_precedes_admission_diagnostic() -> None:
    payload = service_fixtures._fixture("proteins.valid.fasta")
    source = service_fixtures._source("ordered", payload, byte_length=len(payload) - 1)
    source = source.model_copy(
        update={"artifact": service_fixtures._artifact("wrong", "sha256:" + "0" * 64)}
    )

    result = M0103Service().execute(
        service_fixtures._request(source),
        {source.source_id: payload},
    )

    assert result.raw_inputs[0].disposition is RawInputDisposition.REJECTED
    assert [item.code for item in result.raw_inputs[0].diagnostics] == [
        "checksum_mismatch",
        "declared_size_mismatch",
    ]


def test_plugin_rejects_invalid_submission_and_accepts_json_bytearray() -> None:
    payload = service_fixtures._fixture("proteins.valid.fasta")
    source = service_fixtures._source("plugin-coverage", payload)
    request = service_fixtures._request(source)
    plugin = M0103Plugin(M0103Service())

    with pytest.raises(TypeError, match="raw-ingestion submission"):
        plugin.validate(object())

    token = plugin.validate(
        RawIngestionSubmission(
            request=bytearray(request.model_dump_json().encode()),
            sources={source.source_id: payload},
        )
    )
    assert plugin.run(token).disposition is RawInputDisposition.ACCEPTED
