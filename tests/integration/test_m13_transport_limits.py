"""Transport admission checks for standalone M13 adapters."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.adapters.m1303 import app as m1303_app
from glio_proteogen.adapters.m1307 import app as m1307_app
from glio_proteogen.adapters.m1308 import app as m1308_app


@pytest.mark.parametrize(
    ("app", "path"),
    [
        (m1303_app, "/v1/m13-03/construct"),
        (m1307_app, "/v1/m13-07/validate"),
        (m1308_app, "/v1/m13-08/assemble"),
    ],
)
def test_oversized_m13_request_is_rejected_before_parsing(app, path) -> None:
    response = TestClient(app).post(
        path,
        content=b"{" + b"x" * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 2)},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
