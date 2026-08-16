"""FastAPI, Typer, and plugin parity checks for M09-04."""

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator import (
    M0904InputError,
    M0904Service,
    create_app,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_04_probabilistic_estimator.cli import (
    app as cli_app,
)
from tests.modules.c09_complex_stoichiometry.test_m09_04_estimator import _request


def test_api_rejects_unknown_malformed_and_denied_requests() -> None:
    request = _request("stable_support")
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with TestClient(create_app(M0904Service())) as client:
        unknown = client.get("/v1/modules/M09-04/schemas/not-a-contract")
        malformed = client.post("/v1/modules/M09-04/validate", content=b"{bad")
        invalid = client.post("/v1/modules/M09-04/validate", json={})
        denied_response = client.post(
            "/v1/modules/M09-04/validate", json=denied.model_dump(mode="json")
        )
        invalid_verify = client.post("/v1/modules/M09-04/verify", json={})

    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert denied_response.status_code == HTTPStatus.FORBIDDEN
    assert invalid_verify.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in malformed.text.casefold()


def test_api_sanitizes_runtime_rejection() -> None:
    class RejectingService(M0904Service):
        def build(self, _request: object):
            raise M0904InputError("result_noncanonical")

    request = _request("stable_support")
    with TestClient(create_app(RejectingService())) as client:
        response = client.post("/v1/modules/M09-04/estimate", json=request.model_dump(mode="json"))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_validate_estimate_verify_and_no_overwrite(tmp_path) -> None:
    request = _request("stable_support")
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(cli_app, ["export-schema", "verification"])
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    estimated = runner.invoke(
        cli_app, ["estimate", str(request_path), "--output", str(result_path)]
    )
    overwritten = runner.invoke(
        cli_app, ["estimate", str(request_path), "--output", str(result_path)]
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])

    assert schema.exit_code == 0, schema.stdout
    assert validated.exit_code == 0, validated.stdout
    assert estimated.exit_code == 0, estimated.stdout
    assert overwritten.exit_code != 0
    assert verified.exit_code == 0, verified.stdout
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "estimated"


def test_cli_abstention_and_invalid_inputs_are_safe(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    abstention_path = tmp_path / "abstained.json"
    bad_path = tmp_path / "bad.json"
    invalid_path = tmp_path / "invalid.json"
    denied_path = tmp_path / "denied.json"
    invalid_result_path = tmp_path / "invalid-result.json"
    tampered_path = tmp_path / "tampered.json"
    request_path.write_text(
        json.dumps(_request("unsupported PTM").model_dump(mode="json")), encoding="utf-8"
    )
    bad_path.write_text("{", encoding="utf-8")
    invalid_path.write_text("{}", encoding="utf-8")
    denied = _request("stable_support").model_copy(
        update={
            "context": _request("stable_support").context.model_copy(
                update={
                    "references": _request("stable_support").context.references.model_copy(
                        update={
                            "consent": _request(
                                "stable_support"
                            ).context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    denied_path.write_text(json.dumps(denied.model_dump(mode="json")), encoding="utf-8")
    invalid_result_path.write_text("{}", encoding="utf-8")
    valid_result = M0904Service().build(_request("stable_support")).result
    tampered_path.write_text(
        json.dumps(valid_result.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    runner = CliRunner()

    abstained = runner.invoke(
        cli_app, ["estimate", str(request_path), "--output", str(abstention_path)]
    )
    malformed = runner.invoke(cli_app, ["validate", str(bad_path)])
    invalid = runner.invoke(cli_app, ["validate", str(invalid_path)])
    denied_result = runner.invoke(cli_app, ["estimate", str(denied_path)])
    invalid_verify = runner.invoke(cli_app, ["verify", str(invalid_result_path)])
    tampered_verify = runner.invoke(cli_app, ["verify", str(tampered_path)])
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    missing = runner.invoke(cli_app, ["validate", str(tmp_path / "missing.json")])

    assert abstained.exit_code == 1
    assert abstention_path.exists()
    assert malformed.exit_code != 0
    assert invalid.exit_code != 0
    assert denied_result.exit_code != 0
    assert invalid_verify.exit_code != 0
    assert tampered_verify.exit_code != 0
    assert unknown.exit_code != 0
    assert missing.exit_code != 0
