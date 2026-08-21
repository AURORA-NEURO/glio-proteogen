"""Transport admission regressions for M10-08 and M12 adapters."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.adapters.m1008 import create_m1008_app
from glio_proteogen.adapters.m1201 import app as m1201_app
from glio_proteogen.adapters.m1202 import app as m1202_app
from glio_proteogen.adapters.m1203 import app as m1203_app
from glio_proteogen.adapters.m1204 import app as m1204_app
from glio_proteogen.adapters.m1205 import app as m1205_app
from glio_proteogen.adapters.m1206 import app as m1206_app
from glio_proteogen.adapters.m1207 import app as m1207_app
from glio_proteogen.adapters.m1208 import app as m1208_app


@pytest.mark.parametrize(
    ("app", "path"),
    [
        (create_m1008_app(), "/v1/m10-08/publish"),
        (m1201_app, "/v1/modules/M12-01/hypotheses"),
        (m1202_app, "/v1/modules/M12-02/stratify"),
        (m1203_app, "/v1/modules/M12-03/estimate"),
        (m1204_app, "/v1/modules/M12-04/infer"),
        (m1205_app, "/v1/modules/M12-05/evolve"),
        (m1206_app, "/v1/modules/M12-06/assess"),
        (m1207_app, "/v1/modules/M12-07/translate"),
        (m1208_app, "/v1/modules/M12-08/assemble"),
    ],
)
def test_oversized_request_is_rejected_before_json_parsing(app, path) -> None:
    response = TestClient(app).post(
        path,
        content=b"{" + b"x" * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 2)},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
