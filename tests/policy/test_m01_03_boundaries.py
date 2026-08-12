"""Focused ownership, privacy, checksum, and resource boundaries for M01-03."""

from __future__ import annotations

from pathlib import Path

from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    parse_raw_input,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "m01_03"


def test_checksum_mismatch_rejects_before_content_detection() -> None:
    payload = (FIXTURES / "proteins.valid.fasta").read_bytes()

    result = parse_raw_input(
        payload,
        source_id="source.synthetic.checksum",
        expected_sha256="0" * 64,
    )

    assert result.disposition.value == "rejected"
    assert result.detected is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["checksum_mismatch"]


def test_raw_and_decoded_first_excess_are_typed_rejections() -> None:
    plain = (FIXTURES / "proteins.valid.fasta").read_bytes()
    compressed = (FIXTURES / "proteins.valid.fasta.gz").read_bytes()

    raw = parse_raw_input(
        plain,
        source_id="source.synthetic.raw-limit",
        limits=IngestionLimits(max_source_bytes=len(plain) - 1),
    )
    decoded = parse_raw_input(
        compressed,
        source_id="source.synthetic.decoded-limit",
        limits=IngestionLimits(max_decoded_bytes=len(plain) - 1),
    )

    assert raw.disposition.value == decoded.disposition.value == "rejected"
    assert [diagnostic.code for diagnostic in raw.diagnostics] == ["raw_size_limit_exceeded"]
    assert [diagnostic.code for diagnostic in decoded.diagnostics] == [
        "decompressed_size_limit_exceeded"
    ]


def test_result_contains_no_raw_scientific_payload() -> None:
    payload = (FIXTURES / "variants.valid.vcf").read_bytes()

    result = parse_raw_input(payload, source_id="source.synthetic.privacy")
    serialized = result.model_dump_json()

    for forbidden in ("SYNTHETIC_SAMPLE", "synthetic_chr", "var1", '"genotype"', '"rows"'):
        assert forbidden not in serialized
