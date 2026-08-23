from http import HTTPStatus
from pathlib import Path

from fastapi.testclient import TestClient

from glio_proteogen.deployment import DeploymentSettings, create_deployment_app


def _app(tmp_path: Path):
    return create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )


def test_post_operations_expose_request_bodies(tmp_path: Path) -> None:
    schema = _app(tmp_path).openapi()
    missing: list[str] = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in {"post", "put", "patch"} and "requestBody" not in operation:
                missing.append(f"{method.upper()} {path}")
    assert missing == []


def test_external_transport_schema_is_visible_in_openapi(tmp_path: Path) -> None:
    schema = _app(tmp_path).openapi()
    operation = schema["paths"]["/v1/modules/M23-04/validate"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["type"] == "object"
    assert "properties" in request_schema
    assert request_schema["properties"]


def test_swagger_openapi_endpoint_includes_request_body(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/openapi.json")
    assert response.status_code == HTTPStatus.OK
    operation = response.json()["paths"]["/v1/modules/M23-04/validate"]["post"]
    assert operation["requestBody"]["required"] is True
