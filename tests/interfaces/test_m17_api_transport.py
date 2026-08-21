"""Transport-level request/result ceilings for the standalone M17 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1702, m1703, m1705, m1706, m1707

_REQUEST_CASES = (
    (m1702, "/v1/modules/M17-02/align", "M1702_MAX_CANONICAL_REQUEST_BYTES"),
    (m1703, "/v1/modules/M17-03/fuse", "M1703_MAX_CANONICAL_REQUEST_BYTES"),
    (m1705, "/v1/modules/M17-05/present", "M1705_MAX_CANONICAL_REQUEST_BYTES"),
    (m1706, "/v1/modules/M17-06/adjudicate", "M1706_MAX_CANONICAL_REQUEST_BYTES"),
    (m1707, "/v1/modules/M17-07/export", "M1707_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m17_request_limit_is_enforced_before_body_parsing(
    module: Any,
    path: str,
    limit_name: str,
) -> None:
    """Declared request ceilings reject oversized transport metadata first."""

    limit = getattr(module, limit_name)
    app = module.app
    assert isinstance(app, FastAPI)
    with TestClient(app) as client:
        response = client.post(
            path,
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(limit + 1),
            },
        )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


@pytest.mark.parametrize(("module", "path", "limit_name"), _RESULT_CASES)
def test_m17_verify_result_limit_is_enforced_before_body_parsing(
    module: Any,
    path: str,
    limit_name: str,
) -> None:
    """Replay endpoints use the independent result ceiling."""

    limit = getattr(module, limit_name)
    app = module.app
    assert isinstance(app, FastAPI)
    with TestClient(app) as client:
        response = client.post(
            path,
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(limit + 1),
            },
        )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
