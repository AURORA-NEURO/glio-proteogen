"""Checks that concrete model APIs are reachable from the production app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.m24_02.fixture import build_request as m2402_request
from evals.m24_02.fixture import denied_request as m2402_denied_request
from evals.m24_07.fixture import request as m2407_request
from evals.m25_01.fixture import build_request as m2501_request
from evals.m25_02.fixture import build_request as m2502_request
from evals.m25_03.fixture import build_request as m2503_request
from evals.m25_04.fixture import build_request as m2504_request
from evals.m25_05.fixture import build_request as m2505_request
from evals.m25_07.fixture import build_request as m2507_request
from evals.m25_08.fixture import build_request as m2508_request
from evals.m27_07.fixture import build_request as m2707_request
from evals.m27_08.fixture import build_request as m2708_request
from evals.m28_04.fixture import build_request as m2804_request
from fastapi.testclient import TestClient

from glio_proteogen.contracts.m04_07 import M0407_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m23_01 import (
    M2301_MAX_CANONICAL_REQUEST_BYTES,
    M2301_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_02 import (
    M2302_MAX_CANONICAL_REQUEST_BYTES,
    M2302_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_03 import (
    M2303_MAX_CANONICAL_REQUEST_BYTES,
    M2303_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_04 import (
    M2304_MAX_CANONICAL_REQUEST_BYTES,
    M2304_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_05 import (
    M2305_MAX_CANONICAL_REQUEST_BYTES,
    M2305_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_07 import (
    M2307_MAX_CANONICAL_REQUEST_BYTES,
    M2307_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m23_08 import (
    M2308_MAX_CANONICAL_REQUEST_BYTES,
    M2308_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    M2402_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m24_03 import M2403_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m24_04 import M2404_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m24_05 import M2405_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m24_06 import M2406_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m24_07 import M2407_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m24_08 import M2408_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m25_01 import (
    M2501_MAX_CANONICAL_REQUEST_BYTES,
    M2501_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_02 import (
    M2502_MAX_CANONICAL_REQUEST_BYTES,
    M2502_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_03 import (
    M2503_MAX_CANONICAL_REQUEST_BYTES,
    M2503_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_04 import (
    M2504_MAX_CANONICAL_REQUEST_BYTES,
    M2504_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_05 import (
    M2505_MAX_CANONICAL_REQUEST_BYTES,
    M2505_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_06 import (
    M2506_MAX_CANONICAL_REQUEST_BYTES,
    M2506_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_07 import (
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    M2507_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_08 import (
    M2508_MAX_CANONICAL_REQUEST_BYTES,
    M2508_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_01 import M2601_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m26_07 import M2607_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_02 import (
    M2702_MAX_CANONICAL_REQUEST_BYTES,
    M2702_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m27_06 import M2706_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_07 import M2707_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m27_08 import M2708_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.contracts.m28_04 import M2804_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505_module,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_simulation_generator as m2402_module,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    api as m2504_api,
)
from tests.adversarial.test_m2302_contract_adversarial import _request as m2302_request
from tests.adversarial.test_m2307_contract import _request as m2307_request
from tests.contract.test_m23_01_deep import _request as m2301_request
from tests.contract.test_m23_03_hardening import _request as m2303_request
from tests.contract.test_m23_05_hardening import _request as m2305_request
from tests.contract.test_m2304_deep import _request as m2304_request
from tests.contract.test_m2308_deep import _request as m2308_request
from tests.contract.test_m2601_deep import _request
from tests.runtime.test_m15_05_engine import _request as m1505_request
from tests.runtime.test_m27_02_lineage import _request as m2702_request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNSUPPORTED_MEDIA = 415
HTTP_FORBIDDEN = 403
HTTP_PAYLOAD_TOO_LARGE = 413


class _FixtureFailureError(ValueError):
    pass

_MODEL_SCHEMA_ROUTES = (
    ("/v1/contracts/M15-05/request/schema", "GLIO-PROTEOGEN-M15-05"),
    ("/v1/modules/M23-01/schemas/request", "GLIO-PROTEOGEN-M23-01"),
    ("/v1/modules/M23-02/schemas/request", "GLIO-PROTEOGEN-M23-02"),
    ("/v1/modules/M23-03/schemas/request", "GLIO-PROTEOGEN-M23-03"),
    ("/v1/modules/M23-04/schemas/request", "GLIO-PROTEOGEN-M23-04"),
    ("/v1/modules/M23-05/schemas/request", "GLIO-PROTEOGEN-M23-05"),
    ("/v1/modules/M23-07/schemas/request", "GLIO-PROTEOGEN-M23-07"),
    ("/v1/modules/M23-08/schemas/request", "GLIO-PROTEOGEN-M23-08"),
    ("/v1/modules/M24-02/schemas/request", "GLIO-PROTEOGEN-M24-02"),
    ("/v1/modules/M24-03/schemas/request", "GLIO-PROTEOGEN-M24-03"),
    ("/v1/modules/M24-04/schemas/request", "GLIO-PROTEOGEN-M24-04"),
    ("/v1/modules/M24-05/schemas/request", "GLIO-PROTEOGEN-M24-05"),
    ("/v1/modules/M24-06/schemas/request", "GLIO-PROTEOGEN-M24-06"),
    ("/v1/modules/M24-07/schemas/request", "GLIO-PROTEOGEN-M24-07"),
    ("/v1/modules/M24-08/schemas/request", "GLIO-PROTEOGEN-M24-08"),
    ("/v1/modules/M25-01/schemas/request", "GLIO-PROTEOGEN-M25-01"),
    ("/v1/modules/M25-02/schemas/request", "GLIO-PROTEOGEN-M25-02"),
    ("/v1/modules/M25-03/schemas/request", "GLIO-PROTEOGEN-M25-03"),
    ("/v1/modules/M25-04/schemas/request", "GLIO-PROTEOGEN-M25-04"),
    ("/v1/modules/M25-05/schemas/request", "GLIO-PROTEOGEN-M25-05"),
    ("/v1/modules/M25-06/schemas/request", "GLIO-PROTEOGEN-M25-06"),
    ("/v1/modules/M25-07/schemas/request", "GLIO-PROTEOGEN-M25-07"),
    ("/v1/modules/M25-08/schemas/request", "GLIO-PROTEOGEN-M25-08"),
    ("/v1/modules/M26-01/schemas/request", "GLIO-PROTEOGEN-M26-01"),
    ("/m26-02/schema/request", "GLIO-PROTEOGEN-M26-02"),
    ("/v1/modules/M26-03/schemas/request", "GLIO-PROTEOGEN-M26-03"),
    ("/v1/modules/M26-04/schemas/request", "GLIO-PROTEOGEN-M26-04"),
    ("/v1/modules/M26-05/schemas/request", "GLIO-PROTEOGEN-M26-05"),
    ("/v1/modules/M26-06/schemas/request", "GLIO-PROTEOGEN-M26-06"),
    ("/v1/modules/M26-07/schemas/request", "GLIO-PROTEOGEN-M26-07"),
    ("/v1/modules/M26-08/schemas/request", "GLIO-PROTEOGEN-M26-08"),
    ("/v1/modules/M27-03/schemas/request", "GLIO-PROTEOGEN-M27-03"),
    ("/v1/modules/M27-04/schemas/request", "GLIO-PROTEOGEN-M27-04"),
    ("/v1/modules/M27-05/schemas/request", "GLIO-PROTEOGEN-M27-05"),
    ("/v1/modules/M27-06/schemas/request", "GLIO-PROTEOGEN-M27-06"),
    ("/v1/contracts/M27-07/request/schema", "GLIO-PROTEOGEN-M27-07"),
    ("/v1/contracts/M27-08/request/schema", "GLIO-PROTEOGEN-M27-08"),
    ("/v1/contracts/M27-02/output/schema", "GLIO-PROTEOGEN-M27-02"),
    ("/v1/modules/M28-04/schemas/request", "GLIO-PROTEOGEN-M28-04"),
)

_MODEL_OPERATION_ROUTES = (
    "/v1/modules/M15-05/longitudinal-evolution",
    "/v1/modules/M23-01/curate",
    "/v1/modules/M23-02/generate",
    "/v1/modules/M23-03/benchmark",
    "/v1/modules/M23-04/evaluate",
    "/v1/modules/M23-05/evaluate",
    "/v1/modules/M23-07/evaluate",
    "/v1/modules/M23-08/adjudicate",
    "/v1/modules/M24-02/generate",
    "/v1/modules/M24-03/benchmark",
    "/v1/modules/M24-04/evaluate",
    "/v1/modules/M24-05/evaluate",
    "/v1/modules/M24-06/challenge",
    "/v1/modules/M24-07/evaluate",
    "/v1/modules/M24-08/adjudicate",
    "/v1/modules/M25-01/curate",
    "/v1/modules/M25-02/generate",
    "/v1/modules/M25-03/benchmark",
    "/v1/modules/M25-04/evaluate",
    "/v1/modules/M25-05/evaluate",
    "/v1/modules/M25-06/challenge",
    "/v1/modules/M25-07/evaluate",
    "/v1/modules/M25-08/adjudicate",
    "/v1/modules/M26-01/register",
    "/m26-02/construct",
    "/v1/modules/M26-03/execute",
    "/v1/modules/M26-04/publish",
    "/v1/modules/M26-05/emit",
    "/v1/modules/M26-06/evaluate",
    "/v1/modules/M26-07/control",
    "/v1/modules/M26-08/retire",
    "/v1/modules/M27-03/execute",
    "/v1/modules/M27-02/lineage",
    "/v1/modules/M27-04/publish",
    "/v1/modules/M27-05/emit",
    "/v1/modules/M27-06/evaluate",
    "/v1/modules/M27-07/control",
    "/v1/modules/M27-08/retire",
    "/v1/modules/M28-04/publish",
)


def test_production_app_exposes_concrete_model_schema_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        for route, module_id in _MODEL_SCHEMA_ROUTES:
            response = client.get(route)
            assert response.status_code == HTTP_OK, (route, response.text)
            assert response.json()["x-glio-contract"]["moduleId"] == module_id


def test_production_app_exposes_concrete_model_operation_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        for route in _MODEL_OPERATION_ROUTES:
            response = client.post(
                route,
                content=b"{}",
                headers={"content-type": "application/json"},
            )
            assert response.status_code in {HTTP_FORBIDDEN, HTTP_UNPROCESSABLE}, (
                route,
                response.status_code,
                response.text,
            )


def test_production_app_executes_a_deployed_model_route(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    request = _request()

    with TestClient(app) as client:
        registered = client.post(
            "/v1/modules/M26-01/register",
            json=request.model_dump(mode="json"),
        )
        verified = client.post(
            "/v1/modules/M26-01/verify",
            json={"request": request.model_dump(mode="json"), "result": registered.json()},
        )

    assert registered.status_code == HTTP_OK
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True


def test_production_app_executes_new_reference_and_operations_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        human_factors = client.post(
            "/v1/modules/M24-07/evaluate",
            json=m2407_request().model_dump(mode="json"),
        )
        reference_truth = client.post(
            "/v1/modules/M25-01/curate",
            json=m2501_request().model_dump(mode="json"),
        )

    assert human_factors.status_code == HTTP_OK, human_factors.text
    assert reference_truth.status_code == HTTP_OK, reference_truth.text


def test_production_app_executes_latest_change_and_gateway_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        change_control = client.post(
            "/v1/modules/M27-07/control",
            json=m2707_request().model_dump(mode="json"),
        )
        retirement = client.post(
            "/v1/modules/M27-08/retire",
            json=m2708_request().model_dump(mode="json"),
        )
        gateway = client.post(
            "/v1/modules/M28-04/publish",
            json=m2804_request().model_dump(mode="json"),
        )

    assert change_control.status_code == HTTP_OK, change_control.text
    assert retirement.status_code == HTTP_OK, retirement.text
    assert gateway.status_code == HTTP_OK, gateway.text


def test_production_app_executes_variant_peptide_and_proteotype_lanes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    requests = (
        ("/v1/modules/M23-01/curate", m2301_request()),
        ("/v1/modules/M23-02/generate", m2302_request()),
        ("/v1/modules/M23-03/benchmark", m2303_request()),
        ("/v1/modules/M23-04/evaluate", m2304_request()),
        ("/v1/modules/M23-05/evaluate", m2305_request()),
        ("/v1/modules/M23-07/evaluate", m2307_request()),
        ("/v1/modules/M23-08/adjudicate", m2308_request()),
        ("/v1/modules/M27-02/lineage", m2702_request()),
        ("/v1/modules/M25-02/generate", m2502_request()),
        ("/v1/modules/M25-03/benchmark", m2503_request()),
        ("/v1/modules/M25-05/evaluate", m2505_request()),
        ("/v1/modules/M25-07/evaluate", m2507_request()),
        ("/v1/modules/M25-08/adjudicate", m2508_request()),
    )

    with TestClient(app) as client:
        responses = [
            client.post(route, json=request.model_dump(mode="json"))
            for route, request in requests
        ]

    assert all(response.status_code == HTTP_OK for response in responses), [
        (response.status_code, response.text) for response in responses
    ]


def test_production_app_retains_model_specific_request_ceiling(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    with TestClient(app) as client:
        for route, limit in (
            ("/v1/modules/M26-01/validate", M2601_MAX_CANONICAL_REQUEST_BYTES),
            ("/v1/modules/M26-07/validate", M2607_MAX_CANONICAL_REQUEST_BYTES),
        ):
            oversized = b'{"oversized":"' + b"x" * limit + b'"}'
            response = client.post(
                route,
                content=oversized,
                headers={"content-type": "application/json"},
            )
            assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
            assert response.json()["detail"] == "request body exceeds the byte limit"


def test_production_app_limits_body_reading_model_routers(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        for route, limit in (
            ("/v1/modules/M27-05/emit", M2705_MAX_CANONICAL_REQUEST_BYTES),
            ("/v1/modules/M27-06/evaluate", M2706_MAX_CANONICAL_REQUEST_BYTES),
        ):
            oversized = b'{"oversized":"' + b"x" * limit + b'"}'
            response = client.post(
                route,
                content=oversized,
                headers={"content-type": "application/json"},
            )
            assert response.status_code == HTTP_PAYLOAD_TOO_LARGE

        oversized_result = b'{"oversized":"' + b"x" * M2705_MAX_CANONICAL_RESULT_BYTES + b'"}'
        result_response = client.post(
            "/v1/modules/M27-05/verify",
            content=oversized_result,
            headers={"content-type": "application/json"},
        )

    assert result_response.status_code == HTTP_PAYLOAD_TOO_LARGE


def test_production_app_limits_m2402_body_reading_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )

    with TestClient(app) as client:
        oversized_request = b'{"oversized":"' + b"x" * M2402_MAX_CANONICAL_REQUEST_BYTES + b'"}'
        request_response = client.post(
            "/v1/modules/M24-02/validate",
            content=oversized_request,
            headers={"content-type": "application/json"},
        )
        oversized_result = b'{"oversized":"' + b"x" * M2402_MAX_CANONICAL_RESULT_BYTES + b'"}'
        result_response = client.post(
            "/v1/modules/M24-02/verify",
            content=oversized_result,
            headers={"content-type": "application/json"},
        )

    assert request_response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert result_response.status_code == HTTP_PAYLOAD_TOO_LARGE


def test_production_app_limits_new_model_result_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    limits = (
        ("/v1/modules/M23-01/verify", M2301_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-02/verify", M2302_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-03/verify", M2303_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-04/verify", M2304_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-05/verify", M2305_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-07/verify", M2307_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M23-08/verify", M2308_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-01/verify", M2501_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-02/verify", M2502_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-03/verify", M2503_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-04/verify", M2504_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-05/verify", M2505_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-06/verify", M2506_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-07/verify", M2507_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M25-08/verify", M2508_MAX_CANONICAL_RESULT_BYTES),
        ("/v1/modules/M27-02/verify", M2702_MAX_CANONICAL_RESULT_BYTES),
    )
    with TestClient(app) as client:
        for route, limit in limits:
            response = client.post(
                route,
                content=b"",
                headers={
                    "content-type": "application/json",
                    "content-length": str(limit + 1),
                },
            )
            assert response.status_code == HTTP_PAYLOAD_TOO_LARGE, (route, response.text)


def test_production_app_limits_integrated_provisional_model_routes(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    limits = (
        ("/v1/modules/M04-07/support-route", M0407_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-01/validate", M2301_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-02/validate", M2302_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-03/validate", M2303_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-04/validate", M2304_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-05/validate", M2305_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-07/validate", M2307_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M23-08/validate", M2308_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-03/validate", M2403_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-04/validate", M2404_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-05/validate", M2405_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-06/validate", M2406_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-07/validate", M2407_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M24-08/validate", M2408_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-01/validate", M2501_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-02/validate", M2502_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-03/validate", M2503_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-04/validate", M2504_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-05/validate", M2505_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-06/validate", M2506_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-07/validate", M2507_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M25-08/validate", M2508_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M27-02/lineage", M2702_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M27-07/validate", M2707_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M27-08/validate", M2708_MAX_CANONICAL_REQUEST_BYTES),
        ("/v1/modules/M28-04/validate", M2804_MAX_CANONICAL_REQUEST_BYTES),
    )
    with TestClient(app) as client:
        for route, limit in limits:
            oversized = b'{"oversized":"' + b"x" * limit + b'"}'
            response = client.post(
                route,
                content=oversized,
                headers={"content-type": "application/json"},
            )
            assert response.status_code == HTTP_PAYLOAD_TOO_LARGE, (route, response.text)


def test_integrated_api_error_boundaries_are_sanitized() -> None:
    class FailingService:
        def execute(self, request: object) -> object:
            del request
            raise _FixtureFailureError

    with TestClient(m1505_module.api.create_app(FailingService())) as client:
        assert client.get("/v1/contracts/M15-05/unknown/schema").status_code == HTTP_NOT_FOUND
        assert (
            client.post(
                "/v1/modules/M15-05/longitudinal-evolution",
                content=b"[]",
                headers={"content-type": "application/json"},
            ).status_code
            == HTTP_UNPROCESSABLE
        )
        assert (
            client.post(
                "/v1/modules/M15-05/longitudinal-evolution",
                content=b"{}",
                headers={"content-type": "text/plain"},
            ).status_code
            == HTTP_UNSUPPORTED_MEDIA
        )
        denied = m1505_request()
        denied_context = denied.context.model_copy(
            update={
                "references": denied.context.references.model_copy(
                    update={
                        "consent": denied.context.references.consent.model_copy(
                            update={"state": ConsentState.WITHHELD}
                        )
                    }
                )
            }
        )
        assert (
            client.post(
                "/v1/modules/M15-05/longitudinal-evolution",
                json=denied.model_copy(update={"context": denied_context}).model_dump(
                    mode="json"
                ),
            ).status_code
            == HTTP_UNPROCESSABLE
        )
        assert (
            client.post(
                "/v1/modules/M15-05/longitudinal-evolution",
                json=m1505_request().model_dump(mode="json"),
            ).status_code
            == HTTP_UNPROCESSABLE
        )

    with TestClient(m1505_module.api.create_app()) as client:
        assert (
            client.post(
                "/v1/modules/M15-05/longitudinal-evolution",
                json=denied.model_copy(update={"context": denied_context}).model_dump(
                    mode="json"
                ),
            ).status_code
            == HTTP_FORBIDDEN
        )

    class FailingTransportService:
        def execute(self, request: object) -> object:
            del request
            raise _FixtureFailureError

    with TestClient(m2504_api.create_app(FailingTransportService())) as client:
        assert client.post(
            "/v1/modules/M25-04/verify",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code == HTTP_UNPROCESSABLE
        assert client.post(
            "/v1/modules/M25-04/verify",
            content=b"[]",
            headers={"content-type": "application/json"},
        ).status_code == HTTP_UNPROCESSABLE
        assert client.post(
            "/v1/modules/M25-04/evaluate",
            json=m2504_request().model_dump(mode="json"),
        ).status_code == HTTP_UNPROCESSABLE

    with TestClient(m2402_module.api.create_app()) as client:
        assert client.get("/v1/modules/M24-02/schemas").status_code == HTTP_OK
        assert client.get("/v1/modules/M24-02/schemas/unknown").status_code == HTTP_NOT_FOUND
        assert client.post(
            "/v1/modules/M24-02/verify",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code == HTTP_UNPROCESSABLE
        assert client.post(
            "/v1/modules/M24-02/verify",
            content=b"[]",
            headers={"content-type": "application/json"},
        ).status_code == HTTP_UNPROCESSABLE
        denied = client.post(
            "/v1/modules/M24-02/validate",
            json=m2402_denied_request().model_dump(mode="json"),
        )
        assert denied.status_code == HTTP_UNPROCESSABLE
        generated = client.post(
            "/v1/modules/M24-02/generate",
            json=m2402_request().model_dump(mode="json"),
        )
        assert generated.status_code == HTTP_OK
        verified = client.post(
            "/v1/modules/M24-02/verify",
            json=generated.json(),
        )
        assert verified.status_code == HTTP_OK
