"""Transport-level request/result ceilings for the standalone M18 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1801, m1802, m1804, m1805, m1807

_REQUEST_CASES = (
    (m1801, "/v1/modules/M18-01/resolve", "M1801_MAX_CANONICAL_REQUEST_BYTES"),
    (m1802, "/v1/modules/M18-02/align", "M1802_MAX_CANONICAL_REQUEST_BYTES"),
    (m1804, "/v1/modules/M18-04/adapt", "M1804_MAX_CANONICAL_REQUEST_BYTES"),
    (m1805, "/v1/modules/M18-05/present", "M1805_MAX_CANONICAL_REQUEST_BYTES"),
    (m1807, "/v1/modules/M18-07/export", "M1807_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m18_request_limit_is_enforced_before_body_parsing(
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
def test_m18_verify_result_limit_is_enforced_before_body_parsing(
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
