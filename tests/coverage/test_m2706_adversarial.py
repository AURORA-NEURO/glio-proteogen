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
from glio_proteogen.contracts.m27_06.canonical import result_payload_digest
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


@pytest.mark.parametrize(
    ("principal", "resource"),
    [
        ("service:denylisted", "dataset:complex-activity"),
        ("service:m27-06", "dataset:threat-model"),
    ],
)
def test_opaque_subject_labels_do_not_change_action_decision(principal: str, resource: str) -> None:
    """Denial markers belong to action policy, not opaque subject labels."""

    request = build_request(principal=principal, resource=resource, action="read")
    result = M2706SecurityEngine().emit(request)

    assert result.access_decision is not None
    assert result.access_decision.state is AccessDecisionState.ALLOW
    assert result.security_posture is not None
    assert result.security_posture.status.value == "compliant"
    assert result.security_posture.findings == ()


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


def test_result_rejects_self_rehashed_request_subject_mutations() -> None:
    result = M2706Service().emit(build_request())
    assert result.access_decision is not None
    assert result.audit_event is not None

    forged_decision = result.access_decision.model_copy(update={"resource": "dataset:forged"})
    forged = result.model_copy(update={"access_decision": forged_decision})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request subject"):
        ComplexActivitySecurityAccessResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )

    forged_audit = result.audit_event.model_copy(
        update={"decision_state": AccessDecisionState.DENY}
    )
    forged = result.model_copy(update={"audit_event": forged_audit})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="exact request subject and decision"):
        ComplexActivitySecurityAccessResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )


@pytest.mark.parametrize(
    "field",
    ["activity_id", "actor_id", "input_digests", "configuration_digest", "control_decisions"],
)
def test_result_rejects_self_rehashed_provenance_mutations(field: str) -> None:
    result = M2706Service().emit(build_request())
    forged_values: dict[str, object] = {
        "activity_id": "m2706.activity.forged",
        "actor_id": "forged-actor",
        "input_digests": ("sha256:" + "f" * 64,),
        "configuration_digest": "sha256:" + "e" * 64,
        "control_decisions": (
            result.provenance.control_decisions[0].model_copy(
                update={"decision_id": "forged-control"}
            ),
            *result.provenance.control_decisions[1:],
        ),
    }
    forged_provenance = result.provenance.model_copy(update={field: forged_values[field]})
    forged = result.model_copy(update={"provenance": forged_provenance})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="provenance"):
        ComplexActivitySecurityAccessResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )


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


def test_consent_reference_must_bind_granted_context_evidence() -> None:
    request = build_request()
    consent = request.consent_reference
    assert consent is not None
    forged = consent.model_copy(update={"digest": "sha256:" + "f" * 64})
    result = M2706SecurityEngine().emit(request.model_copy(update={"consent_reference": forged}))
    assert result.status.value == "abstained"
    assert result.access_decision is None
    assert result.safe_failure_report is not None
    assert result.abstention_reason == "consent reference does not match granted consent evidence"


def test_access_records_expose_bound_consent_evidence_and_input_digests() -> None:
    request = build_request()
    result = M2706Service().emit(request)
    consent = request.context.references.consent.evidence
    assert result.access_decision is not None
    assert result.access_decision.evidence[0].reference == consent
    assert result.audit_event is not None
    assert result.audit_event.evidence[0].reference == consent
    assert result.security_posture is not None
    consent_check = next(
        check for check in result.security_posture.controls if check.control.value == "consent"
    )
    assert consent_check.evidence[0].reference == consent
    assert consent.digest in result.provenance.input_digests
    assert request.upstream_result.digest in result.provenance.input_digests
