"""Focused metamorphic invariants for the M01-03 byte boundary."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import parse_raw_input

FIXTURES = Path(__file__).parents[1] / "fixtures" / "m01_03"


def test_bytes_and_stream_delivery_are_identical() -> None:
    payload = (FIXTURES / "mzml.valid.mzML").read_bytes()
    keywords = {"source_id": "source.synthetic.delivery", "filename": "input.mzML"}

    assert parse_raw_input(payload, **keywords) == parse_raw_input(BytesIO(payload), **keywords)


def test_filename_cannot_override_content_detection() -> None:
    payload = (FIXTURES / "proteins.valid.fasta").read_bytes()

    result = parse_raw_input(
        payload,
        source_id="source.synthetic.extension",
        filename="misleading.vcf",
    )

    assert result.detected is not None
    assert result.detected.format.value == "FASTA"
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "extension_content_mismatch"
    ]


def test_changing_content_changes_exact_source_digest() -> None:
    payload = (FIXTURES / "proteins.valid.fasta").read_bytes()

    before = parse_raw_input(payload, source_id="source.synthetic.digest")
    after = parse_raw_input(payload + b"\n", source_id="source.synthetic.digest")

    assert before.source_digest != after.source_digest
