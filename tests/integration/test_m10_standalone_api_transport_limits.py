"""Transport-level request ceilings for every standalone M10 FastAPI app."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    api as m1001_api,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (  # noqa: E501
    interfaces as m1002_interfaces,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    interfaces as m1003_interfaces,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    api as m1007_api,
)


@pytest.mark.parametrize(
    ("module", "factory_name", "limit_name", "path"),
    [
        (
            m1001_api,
            "create_app",
            "M1001_MAX_CANONICAL_REQUEST_BYTES",
            "/v1/modules/M10-01/validate",
        ),
        (
            m1002_interfaces,
            "create_m1002_app",
            "M1002_MAX_CANONICAL_REQUEST_BYTES",
            "/v1/m10-02/validate",
        ),
        (
            m1003_interfaces,
            "create_m1003_app",
            "M1003_MAX_CANONICAL_REQUEST_BYTES",
            "/v1/m10-03/validate",
        ),
        (
            m1007_api,
            "create_app",
            "M1007_MAX_CANONICAL_REQUEST_BYTES",
            "/v1/modules/M10-07/validate",
        ),
    ],
)
def test_standalone_m10_request_body_is_rejected_before_parser(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    factory_name: str,
    limit_name: str,
    path: str,
) -> None:
    """A transport overflow must not reach strict JSON or Pydantic parsing."""

    monkeypatch.setattr(module, limit_name, 1)
    factory = getattr(module, factory_name)
    app = factory()
    assert isinstance(app, FastAPI)
    with TestClient(app) as client:
        response = client.post(path, content=b"{}")
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_m1007_verify_uses_result_ceiling_at_transport_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify envelopes use their larger result ceiling, not the request ceiling."""

    monkeypatch.setattr(m1007_api, "M1007_MAX_CANONICAL_RESULT_BYTES", 1)
    app = m1007_api.create_app()
    with TestClient(app) as client:
        response = client.post("/v1/modules/M10-07/verify", content=b"{}")
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
