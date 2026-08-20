"""Adversarial transport-boundary coverage for later governed modules."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    api as m2601_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    api as m2605_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    api as m2606_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    api as m2607_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    api as m2608_api,
)
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import api as m2707_api

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

_REQUEST_ROUTES = (
    (m2601_api.create_app, "/v1/modules/M26-01/validate"),
    (m2605_api.create_m2605_app, "/v1/modules/M26-05/validate"),
    (m2606_api.create_m2606_app, "/v1/modules/M26-06/validate"),
    (m2607_api.create_app, "/v1/modules/M26-07/validate"),
    (m2608_api.create_app, "/v1/modules/M26-08/validate"),
    (m2707_api.create_app, "/v1/modules/M27-07/validate"),
)

_RESULT_ROUTES = (
    (
        m2601_api.create_app,
        "/v1/modules/M26-01/verify",
        m2601_api,
        "M2601_MAX_CANONICAL_RESULT_BYTES",
    ),
    (
        m2605_api.create_m2605_app,
        "/v1/modules/M26-05/verify",
        m2605_api,
        "M2605_MAX_CANONICAL_RESULT_BYTES",
    ),
    (
        m2606_api.create_m2606_app,
        "/v1/modules/M26-06/verify",
        m2606_api,
        "M2606_MAX_CANONICAL_RESULT_BYTES",
    ),
    (
        m2607_api.create_app,
        "/v1/modules/M26-07/verify",
        m2607_api,
        "M2607_MAX_CANONICAL_RESULT_BYTES",
    ),
    (
        m2608_api.create_app,
        "/v1/modules/M26-08/verify",
        m2608_api,
        "M2608_MAX_CANONICAL_RESULT_BYTES",
    ),
    (
        m2707_api.create_app,
        "/v1/modules/M27-07/verify",
        m2707_api,
        "M2707_MAX_CANONICAL_RESULT_BYTES",
    ),
)


@pytest.mark.parametrize(("factory", "path"), _REQUEST_ROUTES)
def test_late_api_request_routes_stream_without_request_body_cache(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[], FastAPI],
    path: str,
) -> None:
    def fail_body(_request: object) -> bytes:
        raise AssertionError

    monkeypatch.setattr("starlette.requests.Request.body", fail_body)
    response = TestClient(factory()).post(path, content=b"{}")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(("factory", "path", "module", "limit_name"), _RESULT_ROUTES)
def test_late_api_replay_routes_bound_result_bodies(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[], FastAPI],
    path: str,
    module: object,
    limit_name: str,
) -> None:
    monkeypatch.setattr(module, limit_name, 8)
    oversized = b"{}" + (b" " * 16)
    response = TestClient(factory()).post(path, content=oversized)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == "request exceeds byte limit"
