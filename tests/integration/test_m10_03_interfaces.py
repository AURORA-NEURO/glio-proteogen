"""API, CLI-neutral, schema, and plugin parity tests for M10-03."""
# ruff: noqa: PLR2004

from __future__ import annotations

import json

import pytest
import typer
from evals.m10_03.run import build_scenario_request
from fastapi.testclient import TestClient

from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator import (
    M1003Plugin,
    M1003Service,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_03_mature_baseline_estimator.interfaces import (  # noqa: E501
    M1003_SCHEMA_NAMES,
    _error_response,
    create_m1003_app,
    estimate_command,
    export_schema,
    export_schema_command,
    validate_command,
)


def test_schema_routes_are_allowlisted() -> None:
    client = TestClient(create_m1003_app())
    for name in M1003_SCHEMA_NAMES:
        response = client.get(f"/v1/m10-03/schema/{name}")
        assert response.status_code == 200
        assert response.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M10-03"
    assert client.get("/v1/m10-03/schema/nope").status_code == 404


def test_api_validate_and_estimate_match_plugin() -> None:
    request = build_scenario_request()
    encoded = request.model_dump_json()
    plugin_result = M1003Plugin(M1003Service()).run(M1003Plugin(M1003Service()).validate(encoded))
    client = TestClient(create_m1003_app())
    validated = client.post("/v1/m10-03/validate", content=encoded)
    estimated = client.post("/v1/m10-03/estimate", content=encoded)
    assert validated.status_code == 200
    assert estimated.status_code == 200
    assert json.loads(estimated.text) == plugin_result.model_dump(mode="json")


def test_api_sanitizes_malformed_json_and_authorization_errors() -> None:
    client = TestClient(create_m1003_app())
    malformed = client.post("/v1/m10-03/validate", content=b'{"request_id":')
    assert malformed.status_code in {400, 422}
    request = build_scenario_request()
    references = request.context.references.model_copy(
        update={
            "support": request.context.references.support.model_copy(update={"state": "rejected"})
        }
    )
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    response = client.post("/v1/m10-03/estimate", content=blocked.model_dump_json())
    assert response.status_code in {400, 403, 422}


def test_typer_commands_and_schema_export_refuse_overwrite(tmp_path) -> None:
    assert export_schema("request")["$id"].endswith(":request")
    schema_path = tmp_path / "request.json"
    export_schema_command("request", schema_path)
    with pytest.raises(Exception, match="overwrite"):
        export_schema_command("request", schema_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(build_scenario_request().model_dump_json(), encoding="utf-8")
    validate_command(request_path)
    estimate_command(request_path, None)


def test_typer_error_and_output_paths(tmp_path) -> None:
    with pytest.raises(Exception, match="unknown M10-03"):
        export_schema_command("unknown", None)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(typer.Exit):
        validate_command(invalid)
    result_path = tmp_path / "result.json"
    request_path = tmp_path / "request-valid.json"
    request_path.write_text(build_scenario_request().model_dump_json(), encoding="utf-8")
    estimate_command(request_path, result_path)
    assert result_path.exists()
    with pytest.raises(Exception, match="overwrite"):
        estimate_command(request_path, result_path)
    export_schema_command("request", None)
    with pytest.raises(typer.Exit):
        estimate_command(invalid, None)
    assert _error_response(ValueError()).status_code == 400
