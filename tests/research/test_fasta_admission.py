"""Adversarial resource-boundary tests for the research FASTA primitive."""

from __future__ import annotations

import io
from typing import BinaryIO, cast

import pytest

from glio_proteogen.research import (
    read_fasta,
)


class _ReadSpy:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requested: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested.append(size)
        return self.payload if size < 0 else self.payload[:size]


def test_binary_stream_is_read_with_a_single_bounded_request() -> None:
    stream = _ReadSpy(b">P1\nACDEFGH\n")
    entries = read_fasta(cast("BinaryIO", stream), max_bytes=64)
    assert entries[0].accession == "P1"
    assert stream.requested == [65]


def test_binary_stream_overflow_is_rejected_before_utf8_or_model_work() -> None:
    stream = _ReadSpy(b">P1\n" + b"A" * 65)
    with pytest.raises(ValueError, match="byte limit"):
        read_fasta(cast("BinaryIO", stream), max_bytes=64)


def test_bytes_and_text_inputs_share_the_same_byte_ceiling() -> None:
    payload = b">P1\nACDEFGH\n"
    with pytest.raises(ValueError, match="byte limit"):
        read_fasta(payload, max_bytes=4)
    with pytest.raises(ValueError, match="byte limit"):
        read_fasta(payload.decode(), max_bytes=4)


def test_entry_and_residue_ceilings_reject_before_unbounded_growth() -> None:
    payload = b">P1\nACDEFGH\n>P2\nACDEFGH\n"
    with pytest.raises(ValueError, match="entry count"):
        read_fasta(payload, max_entries=1)
    with pytest.raises(ValueError, match="residue count"):
        read_fasta(payload, max_residues=13)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_bytes", 0),
        ("max_bytes", 512 * 1024 * 1024 + 1),
        ("max_entries", 0),
        ("max_entries", 2_000_000 + 1),
        ("max_residues", 0),
        ("max_residues", 500_000_000 + 1),
    ],
)
def test_limits_are_closed(name: str, value: int) -> None:
    kwargs = {name: value}
    with pytest.raises(ValueError, match="limit"):
        read_fasta(io.BytesIO(b">P1\nACDEFGH\n"), **kwargs)


def test_binary_stream_must_return_bytes() -> None:
    class _BadStream:
        def read(self, _size: int) -> str:
            return "not bytes"

    with pytest.raises(TypeError, match="bytes"):
        read_fasta(cast("BinaryIO", _BadStream()))
