"""Transport-level request/result ceilings for the standalone M12 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import (
    m1201,
    m1202,
    m1203,
    m1204,
    m1205,
    m1206,
    m1207,
    m1208,
)

_REQUEST_CASES = (
    (m1201, "/v1/modules/M12-01/hypotheses", "M1201_MAX_CANONICAL_REQUEST_BYTES"),
    (m1202, "/v1/modules/M12-02/context", "M1202_MAX_CANONICAL_REQUEST_BYTES"),
    (m1203, "/v1/modules/M12-03/construct", "M1203_MAX_CANONICAL_REQUEST_BYTES"),
    (m1204, "/v1/modules/M12-04/mechanism", "M1204_MAX_CANONICAL_REQUEST_BYTES"),
    (m1205, "/v1/modules/M12-05/longitudinal", "M1205_MAX_CANONICAL_REQUEST_BYTES"),
    (m1206, "/v1/modules/M12-06/simulate", "M1206_MAX_CANONICAL_REQUEST_BYTES"),
    (m1207, "/v1/modules/M12-07/adjudicate", "M1207_MAX_CANONICAL_REQUEST_BYTES"),
    (m1208, "/v1/modules/M12-08/mechanism-dossier", "M1208_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m12_request_limit_is_enforced_before_body_parsing(
    module: Any,
    path: str,
    limit_name: str,
) -> None:
    """Declared request ceilings must reject an oversized Content-Length first."""

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
def test_m12_verify_result_limit_is_enforced_before_body_parsing(
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
