"""Central API/CLI exposure and strict-boundary checks for late lanes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as central_cli
from glio_proteogen.contracts.m20_02 import ProteinSubtypeAlignmentResult
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.contract.test_m19_08_hardening import _request as m1908_request
from tests.modules.c17_metabolomic_lipidomic_integration.test_m20_02_engine import _request

if TYPE_CHECKING:
    from pathlib import Path


_LATE_MODULE_ROUTES = {
    "/v1/modules/M19-01/resolve",
    "/v1/modules/M19-01/verify",
    "/v1/modules/M19-02/align",
    "/v1/modules/M19-02/verify",
    "/v1/modules/M19-03/fusion",
    "/v1/modules/M19-03/verify",
    "/v1/modules/M19-04/adapt",
    "/v1/modules/M19-04/verify",
    "/v1/modules/M19-05/present",
    "/v1/modules/M19-05/verify",
    "/v1/modules/M19-06/adjudication",
    "/v1/modules/M19-06/adjudication/verify",
    "/v1/modules/M19-08/translation-health",
    "/v1/modules/M20-01/resolve",
    "/v1/modules/M20-01/verify",
    "/v1/modules/M20-02/reconcile",
    "/v1/modules/M20-02/verify",
    "/v1/modules/M20-03/fuse",
    "/v1/modules/M20-03/verify",
    "/v1/modules/M20-04/adapt",
    "/v1/modules/M20-04/verify",
}
_LATE_CLI_GROUPS = {
    "m19-01-upstream",
    "m19-02-alignment",
    "m1903-fusion",
    "m1904-intended-use",
    "m19-06-adjudication",
    "m19-05-presentation",
    "m1908-translation-health",
    "m2001-upstream",
    "m20-02-alignment",
    "m20-03-fusion",
    "m20-04-intended-use",
}
HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE = 422
CLI_SUCCESS = 0
CLI_USAGE_ERROR = 2


def _route_paths(app: object) -> set[str]:
    """Collect direct and lazily included FastAPI router paths."""

    paths: set[str] = set()
    visited: set[int] = set()

    def collect(routes: object) -> None:
        if not isinstance(routes, (tuple, list)):
            return
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                paths.add(path)
            included_router = getattr(route, "original_router", None)
            if included_router is not None and id(included_router) not in visited:
                visited.add(id(included_router))
                collect(getattr(included_router, "routes", ()))

    collect(getattr(app, "routes", ()))
    return paths


def test_central_surfaces_register_every_implemented_late_adapter(tmp_path: Path) -> None:
    api = create_app(tmp_path / "events.sqlite")
    # Registration must be direct on the canonical FastAPI app. A nested
    # Starlette Router can look present while contributing no executable
    # FastAPI operations, so assert the actual route table as well as the
    # recursive inventory used for diagnostics.
    direct_paths = {
        path
        for route in api.routes
        for path in (getattr(route, "path", None),)
        if isinstance(path, str) and path in _LATE_MODULE_ROUTES
    }
    assert direct_paths >= _LATE_MODULE_ROUTES
    assert _route_paths(api) >= _LATE_MODULE_ROUTES

    runner = CliRunner()
    for group in sorted(_LATE_CLI_GROUPS):
        help_result = runner.invoke(central_cli, [group, "--help"])
        assert help_result.exit_code == 0, help_result.output


def test_central_m2002_api_and_cli_share_one_canonical_result(tmp_path: Path) -> None:
    request = _request()
    request_bytes = canonical_json_bytes(request)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(request_bytes)

    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        api_result = client.post(
            "/v1/modules/M20-02/reconcile",
            content=request_bytes,
            headers={"content-type": "application/json"},
        )
    cli_result = CliRunner().invoke(
        central_cli,
        ["m20-02-alignment", "reconcile", str(request_path), "--output", str(result_path)],
    )

    assert api_result.status_code == HTTP_OK, api_result.text
    assert cli_result.exit_code == CLI_SUCCESS, cli_result.output
    assert ProteinSubtypeAlignmentResult.model_validate_json(
        api_result.content, strict=True
    ) == ProteinSubtypeAlignmentResult.model_validate_json(result_path.read_bytes(), strict=True)


def test_central_late_routes_reject_malformed_json_before_execution(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        for path in sorted(_LATE_MODULE_ROUTES):
            response = client.post(
                path,
                content=b"{not-json",
                headers={"content-type": "application/json"},
            )
            assert response.status_code == HTTP_UNPROCESSABLE, (path, response.text)
            assert "Traceback" not in response.text


def test_central_m1908_denied_control_is_sanitized(tmp_path: Path) -> None:
    """Central transport must preserve M19-08's fail-closed 403 boundary."""

    request = m1908_request().model_dump(mode="json")
    request["context"]["references"]["consent"]["state"] = "withheld"
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M19-08/translation-health",
            content=canonical_json_bytes(request),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_FORBIDDEN, response.text
    assert "consent" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_central_late_cli_exports_are_json_and_unknown_schema_is_sanitized() -> None:
    runner = CliRunner()
    success = runner.invoke(central_cli, ["m20-03-fusion", "export-schema", "request"])
    failure = runner.invoke(central_cli, ["m20-03-fusion", "export-schema", "unknown"])

    assert success.exit_code == CLI_SUCCESS, success.output
    assert json.loads(success.stdout)["x-glio-contract"]["moduleId"] == ("GLIO-PROTEOGEN-M20-03")
    assert failure.exit_code == CLI_USAGE_ERROR
    assert "unknown M20-03 schema" in failure.output


def test_central_cli_group_names_are_unique() -> None:
    names = [group.name for group in central_cli.registered_groups if group.name is not None]
    assert len(names) == len(set(names)), "duplicate central CLI group registration"
