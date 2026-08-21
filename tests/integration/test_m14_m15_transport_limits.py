"""Transport admission checks for standalone M14/M15 adapters."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.adapters.m1401 import app as m1401_app
from glio_proteogen.adapters.m1402 import app as m1402_app
from glio_proteogen.adapters.m1404 import app as m1404_app
from glio_proteogen.adapters.m1406 import app as m1406_app
from glio_proteogen.adapters.m1407 import app as m1407_app
from glio_proteogen.adapters.m1408 import app as m1408_app
from glio_proteogen.adapters.m1501 import app as m1501_app
from glio_proteogen.adapters.m1503 import app as m1503_app
from glio_proteogen.adapters.m1504 import app as m1504_app
from glio_proteogen.adapters.m1506 import app as m1506_app
from glio_proteogen.adapters.m1507 import app as m1507_app


@pytest.mark.parametrize(
    ("app", "path"),
    [
        (m1401_app, "/v1/modules/M14-01/hypotheses"),
        (m1402_app, "/v1/modules/M14-02/stratify"),
        (m1404_app, "/v1/modules/M14-04/compute"),
        (m1406_app, "/v1/modules/M14-06/compute"),
        (m1407_app, "/v1/modules/M14-07/adjudicate"),
        (m1408_app, "/v1/modules/M14-08/adjudicate"),
        (m1501_app, "/v1/modules/M15-01/estimate"),
        (m1503_app, "/v1/modules/M15-03/compute"),
        (m1504_app, "/v1/modules/M15-04/infer"),
        (m1506_app, "/v1/modules/M15-06/simulate"),
        (m1507_app, "/v1/modules/M15-07/adjudicate"),
    ],
)
def test_oversized_request_is_rejected_before_parsing(app, path) -> None:
    response = TestClient(app).post(
        path,
        content=b"{" + b"x" * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 2)},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
