"""Transport-level request/result ceilings for the standalone M14 APIs."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m1401, m1402, m1404, m1406, m1407, m1408

_REQUEST_CASES = (
    (m1401, "/v1/modules/M14-01/hypotheses", "M1401_MAX_CANONICAL_REQUEST_BYTES"),
    (m1402, "/v1/modules/M14-02/stratify", "M1402_MAX_CANONICAL_REQUEST_BYTES"),
    (m1404, "/v1/modules/M14-04/mechanism", "M1404_MAX_CANONICAL_REQUEST_BYTES"),
    (m1406, "/v1/modules/M14-06/sensitivity", "M1406_MAX_CANONICAL_REQUEST_BYTES"),
    (m1407, "/v1/modules/M14-07/adjudicate", "M1407_MAX_CANONICAL_REQUEST_BYTES"),
    (m1408, "/v1/modules/M14-08/dossier", "M1408_MAX_CANONICAL_REQUEST_BYTES"),
)
_RESULT_CASES = tuple(
    (module, path.rsplit("/", 1)[0] + "/verify", name.replace("REQUEST", "RESULT"))
    for module, path, name in _REQUEST_CASES
)


@pytest.mark.parametrize(("module", "path", "limit_name"), _REQUEST_CASES)
def test_m14_request_limit_is_enforced_before_body_parsing(
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
def test_m14_verify_result_limit_is_enforced_before_body_parsing(
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
