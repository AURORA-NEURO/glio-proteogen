"""Adversarial API, CLI, and canonical-boundary cases for M23-07."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m23_07.fixture import build_request, denied_request, unsupported_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_07 import (
    OperationalConfiguration,
    OperationalDimension,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material import (
    m23_07_human_factors_operational_evaluator as m2307,
)
from tests.adversarial.test_m2307_contract import _request

_HTTP_UNPROCESSABLE = 422


def test_api_rejects_non_object_replay_and_service_json_is_strict() -> None:
    client = TestClient(m2307.create_app(m2307.M2307Service()))
    response = client.post("/v1/modules/M23-07/verify", json=[])
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "must be an object" in response.text
    request = _request()
    parsed = m2307.M2307Service().validate_request(request.model_dump_json())
    assert parsed.request_id == request.request_id


def test_cli_covers_outputless_schema_denial_abstention_and_mismatch(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(denied_request()))
    unsupported_path = tmp_path / "unsupported.json"
    unsupported_path.write_bytes(canonical_json_bytes(unsupported_request()))
    runner = CliRunner()

    schema_result = runner.invoke(m2307.app, ["export-schema", "request"])
    assert schema_result.exit_code == 0
    assert runner.invoke(m2307.app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(m2307.app, ["evaluate", str(denied_path)]).exit_code != 0
    assert runner.invoke(m2307.app, ["evaluate", str(unsupported_path)]).exit_code == 1

    valid_result_path = tmp_path / "result.json"
    valid_result_path.write_bytes(
        canonical_json_bytes(m2307.M2307Service().evaluate(build_request()))
    )

    class ReplayMismatch:
        def replay(self, result: object) -> object:
            typed = cast("Any", result)
            return typed.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    monkeypatch.setattr(m2307.cli, "_SERVICE", ReplayMismatch())
    assert runner.invoke(m2307.app, ["verify", str(valid_result_path)]).exit_code == 1


def test_canonical_dict_projection_and_result_identifier_replay_guard() -> None:
    request = _request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    result = m2307.M2307Service().evaluate(request)
    forged = result.model_copy(update={"result_id": "result.forged"})
    with pytest.raises(m2307.M2307ReplayError, match="identifier"):
        m2307.M2307Service().replay(forged)


def test_contract_closes_configuration_and_fallback_identity() -> None:
    request = _request()
    evidence = request.configuration.evidence
    with pytest.raises(ValueError, match="all operational dimensions"):
        OperationalConfiguration(
            configuration_id="bad-configuration",
            version="0.1.0",
            required_dimensions=(OperationalDimension.FALLBACK,) * 7,
            evidence=evidence,
        )
    duplicate_fallback = request.model_dump(mode="python")
    duplicate_fallback["fallbacks"][1]["scenario_id"] = duplicate_fallback["fallbacks"][0][
        "scenario_id"
    ]
    with pytest.raises(ValueError, match="fallback scenario ids must be unique"):
        type(request)(**duplicate_fallback)
