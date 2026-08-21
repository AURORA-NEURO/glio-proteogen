"""Transport admission checks for M16--M19 standalone adapters."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES
from glio_proteogen.adapters.m1601 import app as m1601_app
from glio_proteogen.adapters.m1602 import app as m1602_app
from glio_proteogen.adapters.m1604 import app as m1604_app
from glio_proteogen.adapters.m1605 import app as m1605_app
from glio_proteogen.adapters.m1607 import app as m1607_app
from glio_proteogen.adapters.m1608 import app as m1608_app
from glio_proteogen.adapters.m1702 import app as m1702_app
from glio_proteogen.adapters.m1703 import app as m1703_app
from glio_proteogen.adapters.m1705 import create_app as create_m1705_app
from glio_proteogen.adapters.m1706 import app as m1706_app
from glio_proteogen.adapters.m1707 import create_app as create_m1707_app
from glio_proteogen.adapters.m1801 import app as m1801_app
from glio_proteogen.adapters.m1802 import create_app as create_m1802_app
from glio_proteogen.adapters.m1804 import app as m1804_app
from glio_proteogen.adapters.m1805 import create_app as create_m1805_app
from glio_proteogen.adapters.m1807 import app as m1807_app
from glio_proteogen.adapters.m1901 import app as m1901_app
from glio_proteogen.adapters.m1902 import app as m1902_app
from glio_proteogen.adapters.m1905 import create_app as create_m1905_app


@pytest.mark.parametrize(
    ("factory", "path"),
    [
        (lambda: m1601_app, "/v1/modules/M16-01/resolve"),
        (lambda: m1602_app, "/v1/modules/M16-02/align"),
        (lambda: m1604_app, "/v1/modules/M16-04/adapt"),
        (lambda: m1605_app, "/v1/modules/M16-05/present"),
        (lambda: m1607_app, "/v1/modules/M16-07/export"),
        (lambda: m1608_app, "/v1/modules/M16-08/monitor"),
        (lambda: m1702_app, "/v1/modules/M17-02/align"),
        (lambda: m1703_app, "/v1/modules/M17-03/fuse"),
        (create_m1705_app, "/v1/modules/M17-05/present"),
        (lambda: m1706_app, "/v1/modules/M17-06/adjudicate"),
        (create_m1707_app, "/v1/modules/M17-07/export"),
        (lambda: m1801_app, "/v1/modules/M18-01/resolve"),
        (create_m1802_app, "/v1/modules/M18-02/align"),
        (lambda: m1804_app, "/v1/modules/M18-04/adapt"),
        (create_m1805_app, "/v1/modules/M18-05/present"),
        (lambda: m1807_app, "/v1/modules/M18-07/export"),
        (lambda: m1901_app, "/v1/modules/M19-01/resolve"),
        (lambda: m1902_app, "/v1/modules/M19-02/align"),
        (create_m1905_app, "/v1/modules/M19-05/present"),
    ],
)
def test_oversized_request_is_rejected_before_parsing(factory, path) -> None:
    response = TestClient(factory()).post(
        path,
        content=b"{" + b"x" * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 2)},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
