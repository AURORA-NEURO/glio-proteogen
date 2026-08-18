"""Adversarial resource-boundary coverage for M27-04 CLI readers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer

from glio_proteogen.contracts.m27_04 import (
    M2704_MAX_CANONICAL_REQUEST_BYTES,
    M2704_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway import cli

Reader = Callable[[Path], object]


def _make_oversized_file(path: Path, limit: int) -> None:
    """Create a sparse limit+1 file without allocating the full test payload."""

    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b" ")


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (cli._read_request, M2704_MAX_CANONICAL_REQUEST_BYTES),
        (cli._read_result, M2704_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m27_04_reader_rejects_oversized_file(
    tmp_path: Path,
    reader: Reader,
    limit: int,
) -> None:
    path = tmp_path / "oversized.json"
    _make_oversized_file(path, limit)
    with pytest.raises(typer.BadParameter):
        reader(path)


def test_m27_04_readers_never_call_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "small.json"
    path.write_bytes(b"{}")

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    for reader in (cli._read_request, cli._read_result):
        with pytest.raises(typer.BadParameter):
            reader(path)
