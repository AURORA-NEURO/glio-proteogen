"""API, CLI, SDK, and plugin parity tests for M26-06."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - pytest resolves the temporary path annotation.

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_06 import (
    ControlStatus,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
    SecurityControlKind,
)
from glio_proteogen.contracts.m26_06.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606SecurityEngine,
    M2606SecurityPlugin,
    M2606SecurityService,
    M2606TokenError,
    SecuritySubmission,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control.api import (
    create_m2606_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control.cli import (
    app as cli_app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control.sdk import (
    M2606SecurityClient,
)
from tests.contract.test_m26_06_provisional import _request

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_FORBIDDEN = 403
_CLI_ABSTAINED = 3


def test_fastapi_validate_evaluate_and_verify_are_canonical() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    client = TestClient(create_m2606_app())

    schemas = client.get("/v1/modules/M26-06/schemas")
    assert schemas.status_code == _HTTP_OK
    assert schemas.json()["output"]["x-glio-contract"]["safeFailureRequired"] is True
    single_schema = client.get("/v1/modules/M26-06/schemas/output")
    assert single_schema.status_code == _HTTP_OK
    validated = client.post("/v1/modules/M26-06/validate", json=payload)
    evaluated = client.post("/v1/modules/M26-06/evaluate", json=payload)
    assert validated.status_code == _HTTP_OK
    assert evaluated.status_code == _HTTP_OK
    result = evaluated.json()
    verified = client.post("/v1/modules/M26-06/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json() == {"verified": True, "result_digest": result["result_digest"]}


def test_fastapi_sanitizes_invalid_and_unauthorized_requests() -> None:
    client = TestClient(create_m2606_app())
    invalid = client.post("/v1/modules/M26-06/evaluate", content=b"{not-json")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert invalid.json()["detail"] == "request does not satisfy the M26-06 contract"

    request = _request()
    references = request.context.references.model_copy(
        update={
            "consent": request.context.references.consent.model_copy(
                update={"state": ConsentState.REVOKED}
            )
        }
    )
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    unauthorized = client.post("/v1/modules/M26-06/evaluate", json=denied.model_dump(mode="json"))
    assert unauthorized.status_code == _HTTP_FORBIDDEN
    assert unauthorized.json()["detail"] == "M26-06 authorization controls rejected request"
    unauthorized_validate = client.post(
        "/v1/modules/M26-06/validate", json=denied.model_dump(mode="json")
    )
    assert unauthorized_validate.status_code == _HTTP_FORBIDDEN


def test_fastapi_validation_error_paths_are_sanitized() -> None:
    request = _request().model_dump(mode="json")

    class RejectingService(M2606SecurityService):
        @staticmethod
        def validate_request(
            _request: object,
        ) -> EvaluateProteomicsSecurityAccessRequest:
            raise ValueError("internal detail must not escape")  # noqa: TRY003

        def execute(self, _request: object) -> ProteomicsSecurityAccessResult:
            raise ValueError("internal detail must not escape")  # noqa: TRY003

    client = TestClient(create_m2606_app(RejectingService()))
    validated = client.post("/v1/modules/M26-06/validate", json=request)
    evaluated = client.post("/v1/modules/M26-06/evaluate", json=request)
    assert validated.status_code == _HTTP_UNPROCESSABLE
    assert evaluated.status_code == _HTTP_UNPROCESSABLE
    assert "internal detail" not in validated.text
    assert "internal detail" not in evaluated.text

    invalid_replay = client.post("/v1/modules/M26-06/verify", json={"result": {"bad": True}})
    assert invalid_replay.status_code == _HTTP_UNPROCESSABLE


def test_api_cli_and_plugin_reject_self_rehashed_security_result(tmp_path: Path) -> None:
    result = M2606SecurityEngine().evaluate(_request())
    assert result.access_decision is not None
    changed = result.access_decision.model_copy(update={"reason": "forged security decision"})
    forged = result.model_copy(update={"access_decision": changed})
    forged = type(forged).model_construct(
        **{
            **forged.__dict__,
            "access_decision": changed,
            "result_digest": result_payload_digest(forged),
        }
    )

    client = TestClient(create_m2606_app())
    response = client.post(
        "/v1/modules/M26-06/verify", json={"result": forged.model_dump(mode="json")}
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "replay envelope is invalid"

    result_path = tmp_path / "forged-result.json"
    result_path.write_bytes(canonical_json_bytes(forged))
    cli = CliRunner().invoke(cli_app, ["verify", str(result_path)])
    assert cli.exit_code != 0
    assert "Traceback" not in cli.output

    with pytest.raises(ValueError, match="replay verification failed"):
        M2606SecurityPlugin().replay(forged)


def test_plugin_requires_opaque_token_and_sdk_matches_service() -> None:
    request = _request()
    plugin = M2606SecurityPlugin()
    token = plugin.validate(SecuritySubmission(canonical_json_bytes(request)))
    assert plugin.validate(SecuritySubmission(request)).request.request_id == request.request_id
    plugin_result = plugin.run(token)
    sdk_result = M2606SecurityClient().evaluate(request)
    assert plugin_result.result_digest == sdk_result.result_digest
    client = M2606SecurityClient()
    assert client.validate(request).request_id == request.request_id
    assert client.verify(sdk_result).result_digest == sdk_result.result_digest
    assert client.evaluate_json(request)["status"] == "evaluated"
    assert plugin.validate_request(request).request_id == request.request_id
    assert plugin.replay(plugin_result).result_digest == plugin_result.result_digest
    with pytest.raises(M2606TokenError):
        M2606SecurityPlugin().run(token)
    with pytest.raises(M2606TokenError):
        plugin.run(object())  # type: ignore[arg-type]
    token._seal = object()
    with pytest.raises(M2606TokenError):
        plugin.run(token)


def test_cli_schema_evaluate_and_verify_refuse_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    runner = CliRunner()

    schema_path = tmp_path / "schema.json"
    schema = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert schema.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["moduleId"] == (
        "GLIO-PROTEOGEN-M26-06"
    )
    overwrite = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert overwrite.exit_code != 0
    stdout_schema = runner.invoke(cli_app, ["export-schema", "output"])
    assert stdout_schema.exit_code == 0
    unknown_schema = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code != 0

    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0

    evaluated = runner.invoke(
        cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
    )
    assert evaluated.exit_code == 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    failed_request = _request()
    failed_declarations = tuple(
        declaration.model_copy(
            update={
                "status": ControlStatus.NOT_EVALUABLE,
                "rationale": "Security evidence is unavailable.",
            }
        )
        if declaration.control is SecurityControlKind.ENCRYPTION
        else declaration
        for declaration in failed_request.control_declarations
    )
    failed_path = tmp_path / "failed.json"
    failed_path.write_bytes(
        canonical_json_bytes(
            type(failed_request).model_validate(
                failed_request.model_copy(update={"control_declarations": failed_declarations})
            )
        )
    )
    abstained = runner.invoke(cli_app, ["evaluate", str(failed_path)])
    assert abstained.exit_code == _CLI_ABSTAINED
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(malformed)]).exit_code != 0
    assert runner.invoke(cli_app, ["verify", str(malformed)]).exit_code != 0
