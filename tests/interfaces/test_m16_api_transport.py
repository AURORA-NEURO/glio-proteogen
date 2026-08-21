"""Transport-level request/result ceilings for the standalone M16 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1601, m1602, m1604, m1605, m1607, m1608

_REQUEST_CASES = (
    (m1601, "/v1/modules/M16-01/resolve", "M1601_MAX_CANONICAL_REQUEST_BYTES"),
    (m1602, "/v1/modules/M16-02/reconcile", "M1602_MAX_CANONICAL_REQUEST_BYTES"),
    (m1604, "/v1/modules/M16-04/adapt", "M1604_MAX_CANONICAL_REQUEST_BYTES"),
    (m1605, "/v1/modules/M16-05/present", "M1605_MAX_CANONICAL_REQUEST_BYTES"),
    (m1607, "/v1/modules/M16-07/export", "M1607_MAX_CANONICAL_REQUEST_BYTES"),
    (m1608, "/v1/modules/M16-08/monitor", "M1608_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m16_request_limit_is_enforced_before_body_parsing(
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
def test_m16_verify_result_limit_is_enforced_before_body_parsing(
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
