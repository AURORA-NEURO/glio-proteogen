"""Black-box FastAPI/Typer parity for standalone provisional adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from evals.m10_05.run import build_request as build_m1005_request
from evals.m11_01.run import build_scenario_request as build_m1101_request
from evals.m11_03.run import request_for as build_m1103_request
from evals.m11_04.run import build_scenario_request as build_m1104_request
from evals.m11_05.run import build_request as build_m1105_request
from evals.m11_06.run import build_scenario_request as build_m1106_request
from evals.m11_08.run import build_request as build_m1108_request
from evals.m13_01.run import build_scenario_request as build_m1301_request
from evals.m13_04.run import build_scenario_request as build_m1304_request
from evals.m13_05.run import build_scenario_request as build_m1305_request
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter
from typer.testing import CliRunner

from glio_proteogen.adapters import (
    m1005,
    m1101,
    m1103,
    m1104,
    m1105,
    m1106,
    m1108,
    m1301,
    m1304,
    m1305,
)
from glio_proteogen.contracts.m10_05 import ProteinRnaConstraintIntegrationResult
from glio_proteogen.contracts.m11_01 import VariantPeptideHypothesisRegistryResult
from glio_proteogen.contracts.m11_03 import VariantPeptideMechanisticFeatureResult
from glio_proteogen.contracts.m11_04 import VariantPeptideMechanismInferenceResult
from glio_proteogen.contracts.m11_05 import VariantPeptideLongitudinalEvolutionResult
from glio_proteogen.contracts.m11_06 import VariantPeptideSensitivitySimulationResult
from glio_proteogen.contracts.m11_08 import VariantPeptideMechanismDossierResult
from glio_proteogen.contracts.m13_01 import ProteotypeHypothesisRegistryResult
from glio_proteogen.contracts.m13_04 import ProteotypeMechanismInferenceResult
from glio_proteogen.contracts.m13_05 import ProteotypeLongitudinalEvolutionResult
from glio_proteogen.kernel.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from fastapi import FastAPI
    from pydantic import BaseModel
    from typer import Typer


HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_BAD_REQUEST = 400
HTTP_UNPROCESSABLE = 422
CLI_OK = 0
_CANARY = "standalone-adapter-sensitive-canary"
_MALFORMED_BODY = ('{"opaque_sample_id":"' + _CANARY + '","broken":').encode()
_M1103_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "m11_03" / "scenarios.json"


@dataclass(frozen=True, slots=True)
class _AdapterCase:
    module_id: str
    api_app: FastAPI
    cli_app: Typer
    schema_path: str
    operation_path: str
    cli_operation: str
    request_builder: Callable[[], BaseModel]
    result_type: type[BaseModel]
    expected_status: str
    malformed_status: int
    invalid_request_status: int


def _build_m1103_fixture_request() -> BaseModel:
    """Use the locked evaluator fixture rather than a hand-written adapter payload."""

    fixture = cast(
        "dict[str, Any]",
        json.loads(_M1103_FIXTURE.read_text(encoding="utf-8")),
    )
    cases = cast("list[dict[str, Any]]", fixture["cases"])
    supported = next(case for case in cases if case["case_id"] == "supported")
    return build_m1103_request(supported)


_CASES = (
    _AdapterCase(
        "GLIO-PROTEOGEN-M10-05",
        m1005.create_m1005_app(),
        m1005.m1005_app,
        "/v1/m10-05/schema/request",
        "/v1/m10-05/integrate",
        "integrate",
        build_m1005_request,
        ProteinRnaConstraintIntegrationResult,
        "integrated",
        HTTP_BAD_REQUEST,
        HTTP_UNPROCESSABLE,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-01",
        m1101.app,
        m1101.m1101_app,
        "/v1/m11-01/schema/request",
        "/v1/modules/M11-01/hypotheses",
        "register",
        build_m1101_request,
        VariantPeptideHypothesisRegistryResult,
        "supported",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-03",
        m1103.app,
        m1103.m1103_app,
        "/v1/m11-03/schema/request",
        "/v1/modules/M11-03/mechanistic-features",
        "construct",
        _build_m1103_fixture_request,
        VariantPeptideMechanisticFeatureResult,
        "constructed",
        HTTP_BAD_REQUEST,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-04",
        m1104.app,
        m1104.m1104_app,
        "/v1/m11-04/schema/request",
        "/v1/modules/M11-04/mechanism",
        "infer",
        build_m1104_request,
        VariantPeptideMechanismInferenceResult,
        "inferred",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-05",
        m1105.app,
        m1105.m1105_app,
        "/v1/m11-05/schema/request",
        "/v1/modules/M11-05/evolve",
        "evolve",
        build_m1105_request,
        VariantPeptideLongitudinalEvolutionResult,
        "modeled",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-06",
        m1106.app,
        m1106.m1106_app,
        "/v1/m11-06/schema/request",
        "/v1/modules/M11-06/perturbations",
        "simulate",
        build_m1106_request,
        VariantPeptideSensitivitySimulationResult,
        "simulated",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M11-08",
        m1108.create_m1108_app(),
        m1108.m1108_app,
        "/v1/m11-08/schema/request",
        "/v1/modules/M11-08/assemble",
        "assemble",
        build_m1108_request,
        VariantPeptideMechanismDossierResult,
        "ready",
        HTTP_BAD_REQUEST,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M13-01",
        m1301.app,
        m1301.m1301_app,
        "/v1/m13-01/schema/request",
        "/v1/modules/M13-01/hypotheses",
        "register",
        build_m1301_request,
        ProteotypeHypothesisRegistryResult,
        "supported",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M13-04",
        m1304.app,
        m1304.m1304_app,
        "/v1/m13-04/schema/request",
        "/v1/modules/M13-04/mechanism",
        "infer",
        build_m1304_request,
        ProteotypeMechanismInferenceResult,
        "inferred",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
    _AdapterCase(
        "GLIO-PROTEOGEN-M13-05",
        m1305.app,
        m1305.m1305_app,
        "/v1/m13-05/schema/request",
        "/v1/modules/M13-05/longitudinal",
        "infer",
        build_m1305_request,
        ProteotypeLongitudinalEvolutionResult,
        "modeled",
        HTTP_UNPROCESSABLE,
        HTTP_FORBIDDEN,
    ),
)


@pytest.mark.integration
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.module_id)
def test_each_standalone_fastapi_schema_operation_and_failure_boundary(
    case: _AdapterCase,
) -> None:
    request_bytes = canonical_json_bytes(case.request_builder())
    with TestClient(case.api_app, raise_server_exceptions=False) as client:
        schema_response = client.get(case.schema_path)
        operation_response = client.post(
            case.operation_path,
            content=request_bytes,
            headers={"content-type": "application/json"},
        )
        malformed_response = client.post(
            case.operation_path,
            content=_MALFORMED_BODY,
            headers={"content-type": "application/json"},
        )
        invalid_response = client.post(
            case.operation_path,
            json={"opaque_sample_id": _CANARY},
        )

    assert schema_response.status_code == HTTP_OK, schema_response.text
    schema = cast("dict[str, Any]", schema_response.json())
    Draft202012Validator.check_schema(schema)
    metadata = cast("dict[str, Any]", schema["x-glio-contract"])
    assert metadata["moduleId"] == case.module_id
    assert metadata["strict"] is True

    assert operation_response.status_code == HTTP_OK, operation_response.text
    TypeAdapter(case.result_type).validate_json(operation_response.content, strict=True)
    assert operation_response.json()["status"] == case.expected_status

    assert malformed_response.status_code == case.malformed_status, malformed_response.text
    assert invalid_response.status_code == case.invalid_request_status, invalid_response.text
    for failure in (malformed_response, invalid_response):
        assert set(failure.json()) == {"detail"}
        assert _CANARY not in failure.text
        assert "Traceback" not in failure.text
        assert str(Path.cwd()) not in failure.text


@pytest.mark.integration
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.module_id)
def test_each_standalone_typer_schema_and_primary_command_match_fastapi(
    case: _AdapterCase,
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.json"
    request_bytes = canonical_json_bytes(case.request_builder())
    request_path.write_bytes(request_bytes)

    with TestClient(case.api_app) as client:
        api_schema = client.get(case.schema_path)
        api_operation = client.post(
            case.operation_path,
            content=request_bytes,
            headers={"content-type": "application/json"},
        )

    runner = CliRunner()
    cli_schema = runner.invoke(case.cli_app, ["export-schema", "request"])
    cli_operation = runner.invoke(case.cli_app, [case.cli_operation, str(request_path)])

    assert api_schema.status_code == HTTP_OK, api_schema.text
    assert cli_schema.exit_code == CLI_OK, cli_schema.output
    assert json.loads(cli_schema.stdout) == api_schema.json()

    assert api_operation.status_code == HTTP_OK, api_operation.text
    assert cli_operation.exit_code == CLI_OK, cli_operation.output
    result_adapter = TypeAdapter(case.result_type)
    api_result = result_adapter.validate_json(api_operation.content, strict=True)
    cli_result = result_adapter.validate_json(cli_operation.stdout, strict=True)
    assert cli_result == api_result
    assert json.loads(cli_operation.stdout)["status"] == case.expected_status
