"""Transport-level request/result ceilings for the standalone M15 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1501, m1503, m1504, m1506, m1507

_REQUEST_CASES = (
    (m1501, "/v1/modules/M15-01/register", "M1501_MAX_CANONICAL_REQUEST_BYTES"),
    (m1503, "/v1/modules/M15-03/features", "M1503_MAX_CANONICAL_REQUEST_BYTES"),
    (m1504, "/v1/modules/M15-04/infer", "M1504_MAX_CANONICAL_REQUEST_BYTES"),
    (m1506, "/v1/modules/M15-06/simulate", "M1506_MAX_CANONICAL_REQUEST_BYTES"),
    (m1507, "/v1/modules/M15-07/adjudicate", "M1507_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m15_request_limit_is_enforced_before_body_parsing(
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
def test_m15_verify_result_limit_is_enforced_before_body_parsing(
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
