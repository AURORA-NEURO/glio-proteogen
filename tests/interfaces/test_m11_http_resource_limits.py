"""HTTP resource-admission regressions for the M11 standalone adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1101, m1102, m1103, m1104, m1105, m1106, m1107, m1108
from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware

_EXPECTED_MAX_BYTES = 8 * 1024 * 1024
_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI


def _apps_and_verify_routes() -> tuple[tuple[str, FastAPI, str], ...]:
    return (
        ("m11-01", m1101.app, "/v1/modules/M11-01/verify"),
        ("m11-02", m1102.m1102_api, "/v1/m11-02/verify"),
        ("m11-03", m1103.app, "/v1/modules/M11-03/verify"),
        ("m11-04", m1104.app, "/v1/modules/M11-04/verify"),
        ("m11-05", m1105.app, "/v1/modules/M11-05/verify"),
        ("m11-06", m1106.app, "/v1/modules/M11-06/verify"),
        ("m11-07", m1107.app, "/v1/modules/M11-07/verify"),
        ("m11-08", m1108.create_m1108_app(), "/v1/modules/M11-08/verify"),
    )


def _body_chunks(limit: int) -> Iterator[bytes]:
    """Yield an over-limit body without a Content-Length header."""

    yield b"x" * limit
    yield b"y"


@pytest.mark.parametrize(
    ("name", "app", "endpoint"),
    _apps_and_verify_routes(),
    ids=[case[0] for case in _apps_and_verify_routes()],
)
def test_m11_http_content_length_is_rejected_before_route(
    name: str,
    app: FastAPI,
    endpoint: str,
) -> None:
    """A forged over-limit declaration cannot reach route parsing."""

    del name, endpoint
    middleware = app.user_middleware[0]
    assert middleware.cls is RequestSizeLimitMiddleware
    assert middleware.kwargs["max_bytes"] == _EXPECTED_MAX_BYTES
    with TestClient(app) as client:
        response = client.post(
            "/missing-route",
            content=b"{}",
            headers={"content-length": str(_EXPECTED_MAX_BYTES + 1)},
        )
    assert response.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


@pytest.mark.parametrize(
    ("name", "app", "endpoint"),
    _apps_and_verify_routes(),
    ids=[case[0] for case in _apps_and_verify_routes()],
)
def test_m11_http_chunked_body_is_rejected_during_stream(
    name: str,
    app: FastAPI,
    endpoint: str,
) -> None:
    """Chunked transfer cannot bypass the byte ceiling when no length is declared."""

    with TestClient(app) as client:
        request = client.build_request(
            "POST",
            endpoint,
            content=_body_chunks(_EXPECTED_MAX_BYTES),
            headers={"content-type": "application/json"},
        )
        assert "content-length" not in request.headers
        response = client.send(request)
    assert response.status_code == _HTTP_PAYLOAD_TOO_LARGE
    detail = response.json()["detail"]
    if name == "m11-02":
        assert detail == [
            {
                "type": "request_too_large",
                "loc": [],
                "msg": "request body exceeds the byte limit",
            }
        ]
    else:
        assert detail == "request body exceeds the byte limit"


@pytest.mark.parametrize(
    ("name", "app", "endpoint"),
    _apps_and_verify_routes(),
    ids=[case[0] for case in _apps_and_verify_routes()],
)
def test_m11_http_invalid_content_length_is_sanitized(
    name: str,
    app: FastAPI,
    endpoint: str,
) -> None:
    """Malformed transport metadata is rejected before any adapter parser runs."""

    del name, endpoint
    with TestClient(app) as client:
        response = client.post(
            "/missing-route",
            content=b"{}",
            headers={"content-length": "not-an-integer"},
        )
    assert response.status_code == _HTTP_BAD_REQUEST
    assert response.json() == {"detail": "invalid content-length"}
