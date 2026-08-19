"""FastAPI, Typer and plugin parity for the M24 provisional runtime lanes."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from evals.m24_02.fixture import request as request_02
from evals.m24_04.fixture import request as request_04
from evals.m24_06.fixture import request as request_06
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_generator as m2402,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_04_external_transport_evaluator as m2404,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_06_robustness_ood_challenge as m2406,
)

_HTTP_OK = HTTPStatus.OK
_HTTP_NOT_FOUND = HTTPStatus.NOT_FOUND
_HTTP_UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY


def _api_parity(
    app: Any,
    request: object,
    route: str,
    schema_count: int,
) -> dict[str, object]:
    client = TestClient(app)
    assert client.get(route + "/schemas").status_code == _HTTP_OK
    assert len(client.get(route + "/schemas").json()) == schema_count
    body = canonical_json_bytes(request)
    assert client.post(route + "/validate", content=body).status_code == _HTTP_OK
    result = client.post(
        route
        + "/"
        + ("generate" if "02" in route else "evaluate" if "04" in route else "challenge"),
        content=body,
    )
    assert result.status_code == _HTTP_OK
    envelope = result.json()
    verified = client.post(route + "/verify", json={"result": envelope})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    return envelope


def test_fastapi_routes_and_replay_are_canonical_for_all_three_modules() -> None:
    _api_parity(m2402.create_app(), request_02(), "/v1/modules/M24-02", 7)
    _api_parity(m2404.create_app(), request_04(), "/v1/modules/M24-04", 8)
    _api_parity(m2406.create_app(), request_06(), "/v1/modules/M24-06", 8)


def test_typer_validate_execute_verify_and_no_overwrite_for_all_three_modules(
    tmp_path: Any,
) -> None:
    cases = (
        (m2402.cli_app, request_02(), "generate"),
        (m2404.cli_app, request_04(), "evaluate"),
        (m2406.cli_app, request_06(), "challenge"),
    )
    runner = CliRunner()
    for index, (app, request, command) in enumerate(cases):
        request_path = tmp_path / f"request-{index}.json"
        result_path = tmp_path / f"result-{index}.json"
        request_path.write_bytes(canonical_json_bytes(request))
        assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
        assert (
            runner.invoke(app, [command, str(request_path), "--output", str(result_path)]).exit_code
            == 0
        )
        original = result_path.read_bytes()
        assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0
        assert (
            runner.invoke(app, [command, str(request_path), "--output", str(result_path)]).exit_code
            != 0
        )
        assert result_path.read_bytes() == original


def test_plugins_require_opaque_submission_and_preserve_replay() -> None:
    cases = (
        (m2402.M2402Plugin(m2402.M2402Service()), m2402.SyntheticTruthSubmission, request_02()),
        (m2404.M2404Plugin(m2404.M2404Service()), m2404.ExternalTransportSubmission, request_04()),
        (m2406.M2406Plugin(m2406.M2406Service()), m2406.RobustnessSubmission, request_06()),
    )
    for plugin, wrapper, request in cases:
        token = plugin.validate(wrapper(json.dumps(request.model_dump(mode="json"))))
        result = plugin.run(token)
        assert plugin.replay(result).result_digest == result.result_digest


def test_api_and_cli_reject_malformed_inputs_without_leaking_details(tmp_path: Any) -> None:
    modules = (
        (m2402, request_02(), "/v1/modules/M24-02", "generate"),
        (m2404, request_04(), "/v1/modules/M24-04", "evaluate"),
        (m2406, request_06(), "/v1/modules/M24-06", "challenge"),
    )
    runner = CliRunner()
    for index, (module, _request, route, command) in enumerate(modules):
        client = TestClient(module.create_app())
        assert client.get(route + "/schemas/unknown").status_code == _HTTP_NOT_FOUND
        invalid = client.post(route + "/validate", content=b"[]")
        assert invalid.status_code == _HTTP_UNPROCESSABLE
        assert "traceback" not in invalid.text.lower()
        assert (
            client.post(route + "/verify", json={"forged": True}).status_code == _HTTP_UNPROCESSABLE
        )
        duplicate = client.post(
            route + "/validate", content=b'{"request_id":"safe","request_id":"forged"}'
        )
        assert duplicate.status_code == _HTTP_UNPROCESSABLE
        request_path = tmp_path / f"bad-request-{index}.json"
        request_path.write_bytes(b"[]")
        assert runner.invoke(module.cli_app, ["export-schema", "unknown"]).exit_code != 0
        assert runner.invoke(module.cli_app, ["validate", str(request_path)]).exit_code != 0
        assert runner.invoke(module.cli_app, [command, str(request_path)]).exit_code != 0
        result_path = tmp_path / f"bad-result-{index}.json"
        result_path.write_bytes(b"{}")
        assert runner.invoke(module.cli_app, ["verify", str(result_path)]).exit_code != 0
