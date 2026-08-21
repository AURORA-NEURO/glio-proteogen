"""Transport-level request/result ceilings for the standalone M13 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import (
    m1301,
    m1302,
    m1303,
    m1304,
    m1305,
    m1307,
    m1308,
)

_REQUEST_CASES = (
    (m1301, "/v1/modules/M13-01/hypotheses", "M1301_MAX_CANONICAL_REQUEST_BYTES"),
    (m1302, "/v1/modules/M13-02/context", "M1302_MAX_CANONICAL_REQUEST_BYTES"),
    (m1303, "/v1/modules/M13-03/features", "M1303_MAX_CANONICAL_REQUEST_BYTES"),
    (m1304, "/v1/modules/M13-04/mechanism", "M1304_MAX_CANONICAL_REQUEST_BYTES"),
    (m1305, "/v1/modules/M13-05/longitudinal", "M1305_MAX_CANONICAL_REQUEST_BYTES"),
    (m1307, "/v1/modules/M13-07/plausibility", "M1307_MAX_CANONICAL_REQUEST_BYTES"),
    (m1308, "/v1/modules/M13-08/dossier", "M1308_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m13_request_limit_is_enforced_before_body_parsing(
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
def test_m13_verify_result_limit_is_enforced_before_body_parsing(
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
