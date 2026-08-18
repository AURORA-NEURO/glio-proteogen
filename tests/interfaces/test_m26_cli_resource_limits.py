"""Adversarial resource-boundary coverage for the M26 CLI readers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer

from glio_proteogen.contracts.m26_02 import (
    M2602_MAX_CANONICAL_REQUEST_BYTES,
    M2602_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_04 import (
    M2604_MAX_CANONICAL_REQUEST_BYTES,
    M2604_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_05 import (
    M2605_MAX_CANONICAL_REQUEST_BYTES,
    M2605_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_06 import (
    M2606_MAX_CANONICAL_REQUEST_BYTES,
    M2606_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_07 import (
    M2607_MAX_CANONICAL_REQUEST_BYTES,
    M2607_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_08 import (
    M2608_MAX_CANONICAL_REQUEST_BYTES,
    M2608_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway import (
    cli as m2604_cli,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    cli as m2605_cli,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    cli as m2606_cli,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    cli as m2607_cli,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    cli as m2608_cli,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service import (
    cli as m2602_cli,
)

Reader = Callable[[Path], object]
ReaderCase = tuple[object, Reader, Reader, int, int]
_READERS: tuple[ReaderCase, ...] = (
    (
        m2602_cli,
        m2602_cli._validated_request,
        m2602_cli._validated_result,
        M2602_MAX_CANONICAL_REQUEST_BYTES,
        M2602_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2604_cli,
        m2604_cli._read_request,
        m2604_cli._read_result,
        M2604_MAX_CANONICAL_REQUEST_BYTES,
        M2604_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2605_cli,
        m2605_cli._read_request,
        m2605_cli._read_result,
        M2605_MAX_CANONICAL_REQUEST_BYTES,
        M2605_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2606_cli,
        m2606_cli._read_request,
        m2606_cli._read_result,
        M2606_MAX_CANONICAL_REQUEST_BYTES,
        M2606_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2607_cli,
        m2607_cli._read_request,
        m2607_cli._read_result,
        M2607_MAX_CANONICAL_REQUEST_BYTES,
        M2607_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2608_cli,
        m2608_cli._read_request,
        m2608_cli._read_result,
        M2608_MAX_CANONICAL_REQUEST_BYTES,
        M2608_MAX_CANONICAL_RESULT_BYTES,
    ),
)


def _make_oversized_file(path: Path, limit: int) -> None:
    """Create a sparse limit+1 file without allocating the full test payload."""

    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b" ")


@pytest.mark.parametrize(
    ("_module", "request_reader", "_result_reader", "request_limit", "_result_limit"),
    _READERS,
)
def test_m26_request_reader_rejects_oversized_file(
    tmp_path: Path,
    _module: object,
    request_reader: Reader,
    _result_reader: Reader,
    request_limit: int,
    _result_limit: int,
) -> None:
    path = tmp_path / "oversized-request.json"
    _make_oversized_file(path, request_limit)
    with pytest.raises((ValueError, typer.BadParameter)):
        request_reader(path)


@pytest.mark.parametrize(
    ("_module", "_request_reader", "result_reader", "_request_limit", "result_limit"),
    _READERS,
)
def test_m26_result_reader_rejects_oversized_file(
    tmp_path: Path,
    _module: object,
    _request_reader: Reader,
    result_reader: Reader,
    _request_limit: int,
    result_limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _make_oversized_file(path, result_limit)
    with pytest.raises((ValueError, typer.BadParameter)):
        result_reader(path)


def test_m26_readers_never_call_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "small.json"
    path.write_bytes(b"{}")

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    for _module, request_reader, result_reader, _request_limit, _result_limit in _READERS:
        with pytest.raises((ValueError, typer.BadParameter)):
            request_reader(path)
        with pytest.raises((ValueError, typer.BadParameter)):
            result_reader(path)
