"""Resource-admission regressions for the M10-07 CLI boundary."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from glio_proteogen.contracts.m10_07 import (
    M1007_MAX_CANONICAL_REQUEST_BYTES,
    M1007_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    cli as m1007_cli,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction.service import (
    M1007Service,
)
from evals.m10_07.run import build_request

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (m1007_cli._read_request, M1007_MAX_CANONICAL_REQUEST_BYTES),
        (m1007_cli._read_object, M1007_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m1007_cli_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized.json"
    _sparse_overflow(path, limit)
    with pytest.raises(m1007_cli.M1007CliError):
        reader(path)


def test_m1007_cli_never_calls_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_request()
    built = m1007_cli._SERVICE.execute(request)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    canonical_path = tmp_path / "canonical.json"
    request_path.write_bytes(request.model_dump_json().encode())
    result_path.write_bytes(built.result.model_dump_json().encode())
    canonical_path.write_bytes(built.canonical_bytes)

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    runner = CliRunner()
    verified = runner.invoke(
        m1007_cli.app,
        ["verify", str(result_path), str(canonical_path)],
    )
    assert verified.exit_code == 0


def test_m1007_result_reader_uses_result_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1007_MAX_CANONICAL_RESULT_BYTES)
    with pytest.raises(m1007_cli.M1007CliError):
        m1007_cli._read_object(path)
