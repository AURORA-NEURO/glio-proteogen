"""Security/access API, CLI, firewall, and replay adversarial coverage."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
import typer
from evals.m27_06.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    M2706_MAX_CANONICAL_RESULT_BYTES,
    AccessDecision,
    AccessDecisionState,
    ComplexActivitySecurityAccessResult,
    SecurityControlKind,
    SecurityFinding,
    SecurityFindingCode,
    SecurityFindingSeverity,
    SecurityPostureRecord,
    contract_json_schemas,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import (
    M2706AuthorizationError,
    M2706Plugin,
    M2706ReplayError,
    M2706SecurityEngine,
    M2706Service,
    SecuritySubmission,
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import cli as cli_module
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access.cli import (
    M2706CliError,
    app,
    evaluate,
    validate,
    verify,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CONTROL_COUNT = 8
_SCHEMA_COUNT = 8


def test_schema_routes_and_api_replay() -> None:
    request = build_request()
    client = TestClient(create_app())
    assert client.get("/v1/modules/M27-06/schemas/request").status_code == _HTTP_OK
    assert client.get("/v1/modules/M27-06/schemas/unknown").status_code == _HTTP_NOT_FOUND
    body = request.model_dump_json()
    assert client.post("/v1/modules/M27-06/validate", content=body).status_code == _HTTP_OK
    result = M2706Service().emit(request)
    verified = client.post("/v1/modules/M27-06/verify", content=result.model_dump_json())
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert (
        client.post("/v1/modules/M27-06/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )


def test_api_rejects_oversized_stream_before_json_parse() -> None:
    client = TestClient(create_app())
    oversized_request = b"{" + b" " * M2706_MAX_CANONICAL_REQUEST_BYTES + b"}"
    oversized_result = b"{" + b" " * M2706_MAX_CANONICAL_RESULT_BYTES + b"}"

    assert (
        client.post("/v1/modules/M27-06/validate", content=oversized_request).status_code
        == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post("/v1/modules/M27-06/verify", content=oversized_result).status_code
        == _HTTP_UNPROCESSABLE
    )


def test_service_rejects_oversized_mapping_result_before_validation() -> None:
    with pytest.raises(ValueError, match="M27-06 result exceeds"):
        M2706Service().replay({"oversized": "x" * M2706_MAX_CANONICAL_RESULT_BYTES})


def test_api_emit_denied_control_is_sanitized() -> None:
    request = build_request()
    context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "withheld"}
                    )
                }
            )
        }
    )
    response = TestClient(create_app()).post(
        "/v1/modules/M27-06/evaluate",
        content=request.model_copy(update={"context": context}).model_dump_json(),
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "private" not in response.text.lower()


def test_cli_output_overwrite_and_invalid_paths(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["export-schema", "unknown"]).exit_code != 0
    assert (
        runner.invoke(
            app, ["export-schema", "request", "--output", str(tmp_path / "schema.json")]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)]).exit_code
        != 0
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert runner.invoke(app, ["validate", str(invalid)]).exit_code != 0


def test_cli_abstention_exit_and_invalid_verify(tmp_path: Path) -> None:
    unsupported = tmp_path / "unsupported.json"
    unsupported.write_text(
        build_request(upstream_media_type="application/json").model_dump_json(), encoding="utf-8"
    )
    runner = CliRunner()
    abstained = runner.invoke(app, ["evaluate", str(unsupported)])
    assert abstained.exit_code == 1
    invalid = tmp_path / "invalid-result.json"
    invalid.write_text("{}", encoding="utf-8")
    assert runner.invoke(app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_bytes_foreign_token_and_seal_tamper() -> None:
    first = M2706Plugin()
    second = M2706Plugin()
    token = first.validate(SecuritySubmission(build_request().model_dump_json()))
    assert first.run(token).status.value == "evaluated"
    with pytest.raises(TypeError):
        second.run(token)
    object.__setattr__(token, "_seal", object())
    with pytest.raises(TypeError):
        first.run(token)


def test_plugin_invalid_submission_and_service_mapping() -> None:
    plugin = M2706Plugin()
    with pytest.raises(TypeError):
        plugin.validate(object())  # type: ignore[arg-type]
    service = M2706Service()
    request = build_request()
    result = service.emit(request.model_dump(mode="json"))
    assert service.replay(result.model_dump(mode="json")) == result


def test_hostile_preflight_fails_without_access() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile")

    with pytest.raises(M2706AuthorizationError):
        M2706Service().emit(Hostile())


def test_duplicate_controls_and_findings_are_rejected() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    payload["requested_controls"] = [SecurityControlKind.LEAST_PRIVILEGE.value] * _CONTROL_COUNT
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)
    result = M2706Service().emit(request)
    assert result.security_posture is not None
    posture = result.security_posture.model_dump(mode="json")
    finding = SecurityFinding(
        finding_id="m2706.finding.duplicate",
        code=SecurityFindingCode.ACCESS_REJECTED,
        severity=SecurityFindingSeverity.ERROR,
        message="duplicate",
    ).model_dump(mode="json")
    posture["findings"] = [finding, finding]
    with pytest.raises(ValueError, match=r".+"):
        SecurityPostureRecord.model_validate(posture, strict=True)


def test_access_consent_and_posture_relational_closure() -> None:
    request = build_request()
    evidence = M2706Service().emit(request).evidence
    payload = {
        "decision_id": "m2706.access.bad",
        "principal": "service:m27-06",
        "resource": "dataset:test",
        "action": "read",
        "state": AccessDecisionState.ALLOW.value,
        "policy_version": "1.0.0",
        "consent_required": True,
        "consent_verified": False,
        "reason": "bad",
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
    with pytest.raises(ValueError, match=r".+"):
        AccessDecision.model_validate(payload, strict=True)


def test_schema_metadata_is_closed() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["leastPrivilegeRequired"] is True
        assert metadata["consentEnforcementRequired"] is True
        assert metadata["unsupportedToNegative"] is False


def test_replay_rejects_all_digest_tampering() -> None:
    service = M2706Service()
    result = service.emit(build_request())
    for field in ("result_id", "request_digest", "result_digest"):
        payload = result.model_dump(mode="json")
        payload[field] = "sha256:" + "f" * 64
        with pytest.raises((ValueError, M2706ReplayError)):
            service.replay(payload)


def test_engine_mapping_bytes_and_direct_replay_closure() -> None:
    request = build_request()
    engine = M2706SecurityEngine()
    assert engine.emit(request.model_dump(mode="json")).status.value == "evaluated"
    assert M2706Service().emit(request.model_dump_json()).status.value == "evaluated"
    result = engine.emit(request)
    for field, value in (
        ("request_digest", "sha256:" + "f" * 64),
        ("result_id", "m2706.result.forged"),
        ("result_digest", "sha256:" + "f" * 64),
    ):
        with pytest.raises(M2706ReplayError):
            engine.replay(result.model_copy(update={field: value}))


def test_request_storage_and_source_closures() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    payload["source_artifacts"] = [payload["source_artifacts"][0]] * 2
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)
    payload = request.model_dump(mode="json")
    payload["upstream_result"]["media_type"] = ""
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)


def test_posture_and_result_projection_closures() -> None:
    result = M2706Service().emit(build_request())
    assert result.security_posture is not None
    posture = result.security_posture.model_dump(mode="json")
    posture["controls"] = posture["controls"][:-1]
    with pytest.raises(ValueError, match=r".+"):
        SecurityPostureRecord.model_validate(posture, strict=True)
    forged = result.model_copy(update={"access_decision": None})
    with pytest.raises(ValueError, match=r".+"):
        ComplexActivitySecurityAccessResult.model_validate(forged, strict=True)


def test_api_parse_and_validate_error_paths() -> None:
    client = TestClient(create_app())
    assert (
        client.post("/v1/modules/M27-06/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    assert (
        client.post(
            "/v1/modules/M27-06/validate",
            content=request.model_copy(update={"context": denied_context}).model_dump_json(),
        ).status_code
        == _HTTP_UNPROCESSABLE
    )


def test_direct_cli_error_and_false_verification_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    result = M2706Service().emit(build_request())
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    evaluate(request_path)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(M2706CliError):
        validate(invalid)
    denied_request = build_request().model_copy(
        update={
            "context": build_request().context.model_copy(
                update={
                    "references": build_request().context.references.model_copy(
                        update={
                            "support": build_request().context.references.support.model_copy(
                                update={"state": "rejected"}
                            )
                        }
                    )
                }
            )
        }
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(denied_request.model_dump_json(), encoding="utf-8")
    with pytest.raises(M2706CliError):
        validate(denied_path)
    with pytest.raises(M2706CliError):
        evaluate(denied_path)

    class ReplayFailure:
        def replay(self, candidate: object) -> object:
            del candidate
            raise ValueError("replay failed")  # noqa: TRY003

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    with pytest.raises(M2706CliError):
        verify(result_path)

    class FalseReplay:
        def replay(self, candidate: object) -> object:
            assert hasattr(candidate, "model_copy")
            return candidate.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    monkeypatch.setattr(cli_module, "_SERVICE", FalseReplay())
    with pytest.raises(typer.Exit):
        verify(result_path)


def test_engine_mutated_instance_replay_guards() -> None:
    engine = M2706SecurityEngine()
    result = engine.emit(build_request())
    for field, value in (
        ("request_digest", "sha256:" + "f" * 64),
        ("result_id", "m2706.result.forged"),
        ("result_digest", "sha256:" + "f" * 64),
    ):
        original = getattr(result, field)
        object.__setattr__(result, field, value)
        try:
            with pytest.raises(M2706ReplayError):
                engine.replay(result)
        finally:
            object.__setattr__(result, field, original)


def test_direct_contract_relational_guards() -> None:
    request = build_request()
    evidence = M2706Service().emit(request).evidence
    with pytest.raises(ValueError, match=r".+"):
        AccessDecision(
            decision_id="m2706.access.invalid",
            principal=request.principal,
            resource=request.resource,
            action=request.action,
            state=AccessDecisionState.ALLOW,
            policy_version=request.policy_version,
            consent_required=True,
            consent_verified=False,
            reason="invalid consent",
            evidence=evidence,
        )
    posture = M2706Service().emit(request).security_posture
    assert posture is not None
    with pytest.raises(ValueError, match=r".+"):
        type(posture)(
            posture_id=posture.posture_id,
            version=posture.version,
            status=posture.status,
            controls=(posture.controls[0],) * _CONTROL_COUNT,
            findings=posture.findings,
            evidence=posture.evidence,
        )
    with pytest.raises(ValueError, match=r".+"):
        type(posture)(
            posture_id=posture.posture_id,
            version=posture.version,
            status=posture.status,
            controls=(*posture.controls[:-1], posture.controls[0]),
            findings=posture.findings,
            evidence=posture.evidence,
        )
