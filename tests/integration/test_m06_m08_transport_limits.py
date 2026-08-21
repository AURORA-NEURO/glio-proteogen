"""Transport admission regressions for the M06--M08 standalone adapters."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.adapters.m0608 import create_m0608_app
from glio_proteogen.adapters.m0703 import create_m0703_app
from glio_proteogen.adapters.m0704 import create_m0704_app
from glio_proteogen.adapters.m0708 import create_m0708_app
from glio_proteogen.adapters.m08_04 import create_m0804_app


@pytest.mark.parametrize(
    ("factory", "path"),
    [
        (create_m0608_app, "/v1/m06-08/evidence/publish"),
        (create_m0703_app, "/v1/m07-03/baseline/estimate"),
        (create_m0704_app, "/v1/m07-04/quality/compute"),
        (create_m0708_app, "/v1/m07-08/provenance/resolve"),
        (create_m0804_app, "/v1/m08-04/estimate"),
    ],
)
def test_oversized_declared_request_is_rejected_before_model_parsing(factory, path) -> None:
    client = TestClient(factory())
    response = client.post(
        path,
        content=b"{" + b"x" * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 2)},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert "validation" not in response.text.lower()


@pytest.mark.parametrize(
    ("factory", "path"),
    [
        (create_m0608_app, "/v1/m06-08/evidence/verify"),
        (create_m0703_app, "/v1/m07-03/baseline/verify"),
        (create_m0704_app, "/v1/m07-04/quality/verify"),
        (create_m0708_app, "/v1/m07-08/provenance/verify"),
        (create_m0804_app, "/v1/m08-04/verify"),
    ],
)
def test_verify_uses_independent_result_transport_ceiling(factory, path) -> None:
    client = TestClient(factory())
    response = client.post(
        path,
        content=b"{" + b"x" * (MAX_REQUEST_BYTES + 1) + b"}",
        headers={
            "content-type": "application/json",
            "content-length": str(MAX_REQUEST_BYTES + 2),
        },
    )
    assert response.status_code != HTTPStatus.REQUEST_ENTITY_TOO_LARGE
