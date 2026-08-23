"""Regression checks for request/result transport ceilings on current model APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

from glio_proteogen.contracts.m26_01 import M2601_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_02 import M2602_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_03 import M2603_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_04 import M2604_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_05 import M2605_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_06 import M2606_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_07 import M2607_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_08 import M2608_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_03 import M2703_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_04 import M2704_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_05 import M2705_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_06 import M2706_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.modules.c20_biomarker_panel import (
    m26_08_retirement_archival_knowledge_transfer as m2608_module,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service.api import (
    create_app as create_m2601_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway.api import (
    create_app as create_m2604_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry.api import (
    create_m2605_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control.api import (
    create_m2606_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback.api import (
    create_app as create_m2607_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.api import (
    create_app as create_m2704_app,
)
from glio_proteogen.modules.c21_reference_material import (
    m26_03_reproducible_pipeline_orchestrator as m2603_module,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.api import (
    create_m2602_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    api as m2703_api,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry.api import (
    create_app as create_m2705_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access.api import (
    create_app as create_m2706_app,
)

_JSON_HEADERS = {"content-type": "application/json"}
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_FOUND = 404
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422


@pytest.mark.parametrize(
    ("factory", "route", "request_limit"),
    [
        (create_m2601_app, "/v1/modules/M26-01/verify", M2601_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2602_app, "/m26-02/verify", M2602_MAX_CANONICAL_REQUEST_BYTES),
        (m2603_module.create_app, "/v1/modules/M26-03/verify", M2603_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2604_app, "/v1/modules/M26-04/verify", M2604_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2605_app, "/v1/modules/M26-05/verify", M2605_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2606_app, "/v1/modules/M26-06/verify", M2606_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2607_app, "/v1/modules/M26-07/verify", M2607_MAX_CANONICAL_REQUEST_BYTES),
        (m2608_module.create_app, "/v1/modules/M26-08/verify", M2608_MAX_CANONICAL_REQUEST_BYTES),
        (m2703_api.create_app, "/v1/modules/M27-03/verify", M2703_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2704_app, "/v1/modules/M27-04/verify", M2704_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2705_app, "/v1/modules/M27-05/verify", M2705_MAX_CANONICAL_REQUEST_BYTES),
        (create_m2706_app, "/v1/modules/M27-06/verify", M2706_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_verify_route_uses_result_ceiling(
    factory: Callable[[], FastAPI], route: str, request_limit: int
) -> None:
    """A body above request size but below result size reaches result parsing."""

    body = b'{"oversized":"' + (b"x" * request_limit) + b'"}'
    response = TestClient(factory()).post(route, content=body, headers=_JSON_HEADERS)

    assert response.status_code == _HTTP_UNPROCESSABLE


@pytest.mark.parametrize(
    ("factory", "schema_route", "verify_route"),
    [
        (
            create_m2601_app,
            "/v1/modules/M26-01/schemas/unknown",
            "/v1/modules/M26-01/verify",
        ),
        (create_m2602_app, "/m26-02/schema/unknown", "/m26-02/verify"),
        (
            m2603_module.create_app,
            "/v1/modules/M26-03/schemas/unknown",
            "/v1/modules/M26-03/verify",
        ),
        (
            create_m2604_app,
            "/v1/modules/M26-04/schemas/unknown",
            "/v1/modules/M26-04/verify",
        ),
        (
            create_m2605_app,
            "/v1/modules/M26-05/schemas/unknown",
            "/v1/modules/M26-05/verify",
        ),
        (
            create_m2606_app,
            "/v1/modules/M26-06/schemas/unknown",
            "/v1/modules/M26-06/verify",
        ),
        (
            create_m2607_app,
            "/v1/modules/M26-07/schemas/unknown",
            "/v1/modules/M26-07/verify",
        ),
        (
            m2608_module.create_app,
            "/v1/modules/M26-08/schemas/unknown",
            "/v1/modules/M26-08/verify",
        ),
        (
            m2703_api.create_app,
            "/v1/modules/M27-03/schemas/unknown",
            "/v1/modules/M27-03/verify",
        ),
        (
            create_m2704_app,
            "/v1/modules/M27-04/schemas/unknown",
            "/v1/modules/M27-04/verify",
        ),
        (
            create_m2705_app,
            "/v1/modules/M27-05/schemas/unknown",
            "/v1/modules/M27-05/verify",
        ),
        (
            create_m2706_app,
            "/v1/modules/M27-06/schemas/unknown",
            "/v1/modules/M27-06/verify",
        ),
    ],
)
def test_current_model_routes_sanitize_unknown_schema_and_malformed_verify(
    factory: Callable[[], FastAPI], schema_route: str, verify_route: str
) -> None:
    client = TestClient(factory())

    assert client.get(schema_route).status_code == _HTTP_NOT_FOUND
    unsupported = client.post(
        verify_route,
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    response = client.post(verify_route, content=b"not-json", headers=_JSON_HEADERS)

    assert unsupported.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert response.status_code in {_HTTP_BAD_REQUEST, _HTTP_UNPROCESSABLE}
