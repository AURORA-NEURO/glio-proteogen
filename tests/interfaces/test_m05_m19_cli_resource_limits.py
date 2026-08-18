"""Resource-admission regressions for the M05-08 and M19-07 CLIs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m05_08 import M0508_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m19_07 import (
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    M1907_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging import (
    cli as m0508_cli,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    api as m1907_api,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    cli as m1907_cli,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    plugin as m1907_plugin,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export.service import (  # noqa: E501
    M1907Service,
)
from tests.contract.test_m19_07_deep import _request

_SMALL_LIMIT = 2
_UNPROCESSABLE_CONTENT = 422

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (m0508_cli._read, M0508_MAX_CANONICAL_REQUEST_BYTES),
        (m1907_cli._read_request, M1907_MAX_CANONICAL_REQUEST_BYTES),
        (m1907_cli._read_result, M1907_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_cli_readers_reject_sparse_oversize_before_json_parse(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized.json"
    _sparse_overflow(path, limit)
    with pytest.raises(RequestBodyTooLargeError):
        reader(path)


def test_cli_readers_never_call_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "small.json"
    path.write_bytes(b"{}")

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    assert m0508_cli._read(path) == b"{}"
    with pytest.raises(ValidationError):
        m1907_cli._read_request(path)
    with pytest.raises(ValidationError):
        m1907_cli._read_result(path)


def test_m19_result_ceiling_is_used_by_api_and_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = M1907Service().execute(_request())
    result_bytes = canonical_json_bytes(result.model_dump(mode="json"))
    assert len(result_bytes) > _SMALL_LIMIT

    monkeypatch.setattr(m1907_api, "M1907_MAX_CANONICAL_RESULT_BYTES", _SMALL_LIMIT)
    with TestClient(m1907_api.create_m1907_app()) as client:
        response = client.post("/v1/modules/M19-07/verify", content=result_bytes)
    assert response.status_code == _UNPROCESSABLE_CONTENT

    result_path = tmp_path / "result.json"
    result_path.write_bytes(result_bytes)
    monkeypatch.setattr(m1907_cli, "M1907_MAX_CANONICAL_RESULT_BYTES", _SMALL_LIMIT)
    with pytest.raises(RequestBodyTooLargeError):
        m1907_cli._read_result(result_path)

    monkeypatch.setattr(m1907_plugin, "M1907_MAX_CANONICAL_RESULT_BYTES", _SMALL_LIMIT)
    with pytest.raises(StrictJsonError, match="byte limit"):
        m1907_plugin.M1907Plugin().verify(result_bytes)
