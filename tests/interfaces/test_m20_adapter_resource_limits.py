"""Resource-admission regressions for the standalone M20 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m2001, m2002, m2003, m2004
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m20_01 import (
    M2001_MAX_CANONICAL_REQUEST_BYTES,
    M2001_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m20_02 import (
    M2002_MAX_CANONICAL_REQUEST_BYTES,
    M2002_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m20_03 import (
    M2003_MAX_CANONICAL_REQUEST_BYTES,
    M2003_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m20_04 import (
    M2004_MAX_CANONICAL_REQUEST_BYTES,
    M2004_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from fastapi import FastAPI

_HTTP_PAYLOAD_TOO_LARGE = 413


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m2001_request(path: Path) -> object:
    return m2001._load_request(path)


def _m2002_request(path: Path) -> object:
    return m2002._load_request(path)


def _m2003_request(path: Path) -> object:
    return m2003._load_request(path)


def _m2004_request(path: Path) -> object:
    return m2004._load_request(path)


def _m2001_result(path: Path) -> object:
    return m2001._read_result(path)


def _m2002_result(path: Path) -> object:
    return m2002._read_result(path)


def _m2003_result(path: Path) -> object:
    return m2003._read_result(path)


def _m2004_result(path: Path) -> object:
    return m2004._read_result(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m2001_request, M2001_MAX_CANONICAL_REQUEST_BYTES),
        (_m2002_request, M2002_MAX_CANONICAL_REQUEST_BYTES),
        (_m2003_request, M2003_MAX_CANONICAL_REQUEST_BYTES),
        (_m2004_request, M2004_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m20_request_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-request.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m2001_result, M2001_MAX_CANONICAL_RESULT_BYTES),
        (_m2002_result, M2002_MAX_CANONICAL_RESULT_BYTES),
        (_m2003_result, M2003_MAX_CANONICAL_RESULT_BYTES),
        (_m2004_result, M2004_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m20_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


@pytest.mark.parametrize(
    ("app", "command", "limit"),
    [
        (m2001.m2001_app, "verify", M2001_MAX_CANONICAL_RESULT_BYTES),
        (m2002.m2002_app, "verify", M2002_MAX_CANONICAL_RESULT_BYTES),
        (m2003.m2003_app, "verify", M2003_MAX_CANONICAL_RESULT_BYTES),
        (m2004.m2004_app, "verify", M2004_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m20_cli_result_overflow_is_sanitized(
    tmp_path: Path,
    app: typer.Typer,
    command: str,
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    result = CliRunner().invoke(app, [command, str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


@pytest.mark.parametrize(
    ("app", "path", "limit"),
    [
        (m2001.app, "/v1/modules/M20-01/verify", M2001_MAX_CANONICAL_RESULT_BYTES),
        (m2002.app, "/v1/modules/M20-02/verify", M2002_MAX_CANONICAL_RESULT_BYTES),
        (m2003.app, "/v1/modules/M20-03/verify", M2003_MAX_CANONICAL_RESULT_BYTES),
        (m2004.app, "/v1/modules/M20-04/verify", M2004_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m20_fastapi_transport_rejects_oversized_result_before_route_parsing(
    app: FastAPI,
    path: str,
    limit: int,
) -> None:
    response = TestClient(app).post(
        path,
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(limit + 1),
        },
    )
    assert response.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


@pytest.mark.parametrize(
    ("app", "path", "limit"),
    [
        (m2001.app, "/v1/modules/M20-01/resolve", M2001_MAX_CANONICAL_RESULT_BYTES),
        (m2002.app, "/v1/modules/M20-02/reconcile", M2002_MAX_CANONICAL_RESULT_BYTES),
        (m2003.app, "/v1/modules/M20-03/fuse", M2003_MAX_CANONICAL_RESULT_BYTES),
        (m2004.app, "/v1/modules/M20-04/adapt", M2004_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m20_fastapi_transport_rejects_oversized_request_before_route_parsing(
    app: FastAPI,
    path: str,
    limit: int,
) -> None:
    response = TestClient(app).post(
        path,
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(limit + 1),
        },
    )
    assert response.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_m20_fastapi_transport_rejects_oversized_chunked_body() -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(9):
            yield b"x" * (1024 * 1024)

    response = TestClient(m2001.app).post(
        "/v1/modules/M20-01/resolve",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_m20_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m2001.py", "m2002.py", "m2003.py", "m2004.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
