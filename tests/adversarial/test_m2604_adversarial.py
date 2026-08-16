"""Adversarial closure, parser, authorization, replay, and boundary tests."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_04 import (
    AccessProtocol,
    AccessSurface,
    AsyncJobRecord,
    AuthorizationDecision,
    CompatibilityStatus,
    GatewayStatus,
    JobStatus,
    OperationStatus,
    ProteinSubtypeAccessSurfaceResult,
    PublishProteinSubtypeAccessSurfaceRequest,
    contract_json_schema,
)
from glio_proteogen.contracts.m26_04.canonical import canonical_request_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway import (
    GatewaySubmission,
    M2604AuthorizationError,
    M2604Client,
    M2604GatewayEngine,
    M2604Plugin,
    M2604ReplayError,
    M2604Service,
    M2604TokenError,
    api,
    cli,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway.engine import (
    _findings,
    publish_protein_subtype_access_surface,
)
from tests.contract.test_m2604_contract import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_strict_plugin_rejects_duplicate_json_keys() -> None:
    plugin = M2604Plugin()
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        plugin.validate(GatewaySubmission('{"request_id":"one","request_id":"two"}'))


def test_service_rejects_hostile_mapping_before_model_traversal() -> None:
    class HostileMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            if key == "context":
                raise RuntimeError
            return super().get(key, default)

    with pytest.raises(M2604AuthorizationError):
        M2604Service().publish(HostileMapping())


def test_engine_rejects_forged_plugin_capability() -> None:
    with pytest.raises(TypeError, match="validated request token"):
        M2604Plugin().run(object())  # type: ignore[arg-type]


def test_replay_rejects_result_id_and_digest_tampering() -> None:
    engine = M2604GatewayEngine()
    result = engine.publish(_request())
    with pytest.raises(M2604ReplayError):
        engine.replay(result.model_copy(update={"result_id": "m2604.forged"}))
    with pytest.raises(M2604ReplayError):
        engine.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))


def test_replay_rejects_request_digest_payload_and_untyped_candidates() -> None:
    engine = M2604GatewayEngine()
    result = engine.publish(_request())
    with pytest.raises(M2604ReplayError):
        engine.replay(result.model_copy(update={"request_digest": "sha256:" + "1" * 64}))
    with pytest.raises(M2604ReplayError):
        engine.replay(result.model_copy(update={"findings": ()}))
    with pytest.raises(M2604ReplayError):
        engine.replay(object())  # type: ignore[arg-type]


def test_contract_rejects_duplicate_operation_ids_after_revalidation() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["operations"] = (request.operations[0], request.operations[0])
    with pytest.raises(ValidationError, match="gateway operation ids"):
        PublishProteinSubtypeAccessSurfaceRequest.model_validate(payload)


def test_request_rejects_unknown_operation_references() -> None:
    request = _request()
    foreign = request.authorizations[0].model_copy(
        update={"operation_id": "m2604.operation.foreign"}
    )
    with pytest.raises(ValidationError, match="unknown operation"):
        PublishProteinSubtypeAccessSurfaceRequest.model_validate(
            request.model_copy(update={"authorizations": (foreign,)}).model_dump(mode="python")
        )


def test_disabled_operation_abstains_and_preserves_finding() -> None:
    request = _request()
    disabled = request.operations[0].model_copy(update={"status": OperationStatus.DISABLED})
    result = M2604GatewayEngine().publish(request.model_copy(update={"operations": (disabled,)}))
    assert result.status.value == "abstained"
    assert result.access_surface is None
    assert any(item.code.value == "operation_unauthorized" for item in result.findings)


def test_terminal_async_job_invariants_are_fail_closed() -> None:
    request = _request()
    job = request.jobs[0]
    with pytest.raises(ValidationError, match="succeeded async job"):
        AsyncJobRecord.model_validate(
            job.model_copy(update={"result_artifact": None}).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="failed async job"):
        AsyncJobRecord.model_validate(
            job.model_copy(
                update={"status": JobStatus.FAILED, "result_artifact": None, "error_code": None}
            ).model_dump(mode="python")
        )


def test_configuration_and_surface_reference_closure_is_exhaustive() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="supported gateway protocols"):
        type(request.configuration).model_validate(
            request.configuration.model_copy(
                update={"supported_protocols": (AccessProtocol.API, AccessProtocol.API)}
            ).model_dump(mode="python")
        )
    operation = request.operations[0]
    surface_kwargs = {
        "surface_id": "m2604.surface.adversarial",
        "version": "1.0.0",
        "operations": (operation,),
        "authorizations": request.authorizations,
        "idempotency_records": request.idempotency_records,
        "jobs": request.jobs,
        "compatibility_rules": request.compatibility_rules,
        "errors": request.errors,
        "audit_events": request.audit_events,
        "configuration": request.configuration,
        "evidence": request.operations[0].evidence,
    }
    with pytest.raises(ValidationError, match="authorization references"):
        AccessSurface.model_validate(
            {
                **surface_kwargs,
                "authorizations": (
                    request.authorizations[0].model_copy(
                        update={"operation_id": "m2604.operation.other"}
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="async job references"):
        AccessSurface.model_validate(
            {
                **surface_kwargs,
                "jobs": (
                    request.jobs[0].model_copy(update={"operation_id": "m2604.operation.other"}),
                ),
            }
        )
    with pytest.raises(ValidationError, match="idempotency record references"):
        AccessSurface.model_validate(
            {
                **surface_kwargs,
                "idempotency_records": (
                    request.idempotency_records[0].model_copy(
                        update={"operation_id": "m2604.operation.other"}
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="compatibility rule references"):
        AccessSurface.model_validate(
            {
                **surface_kwargs,
                "compatibility_rules": (
                    request.compatibility_rules[0].model_copy(
                        update={"operation_id": "m2604.operation.other"}
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="audit event references"):
        AccessSurface.model_validate(
            {
                **surface_kwargs,
                "audit_events": (
                    request.audit_events[0].model_copy(
                        update={"operation_id": "m2604.operation.other"}
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="operation ids"):
        AccessSurface.model_validate({**surface_kwargs, "operations": (operation, operation)})


def test_request_required_modalities_and_result_closure_are_fail_closed() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = request.source_artifacts[:2]
    with pytest.raises(ValidationError, match="every declared gateway modality"):
        PublishProteinSubtypeAccessSurfaceRequest.model_validate(payload)
    engine = M2604GatewayEngine()
    published = engine.publish(request)
    with pytest.raises(ValidationError, match="request digest"):
        ProteinSubtypeAccessSurfaceResult.model_validate(
            published.model_copy(update={"request_digest": sha256_digest("forged")}).model_dump(
                mode="python"
            )
        )
    denied = request.authorizations[0].model_copy(update={"decision": AuthorizationDecision.DENY})
    abstained = engine.publish(request.model_copy(update={"authorizations": (denied,)}))
    with pytest.raises(ValidationError, match="published result"):
        ProteinSubtypeAccessSurfaceResult.model_validate(
            abstained.model_copy(update={"status": GatewayStatus.PUBLISHED}).model_dump(
                mode="python"
            )
        )
    with pytest.raises(ValidationError, match="abstained result"):
        ProteinSubtypeAccessSurfaceResult.model_validate(
            published.model_copy(update={"status": GatewayStatus.ABSTAINED}).model_dump(
                mode="python"
            )
        )


def test_public_entrypoint_and_mapping_canonical_helpers_are_stable() -> None:
    request = _request()
    result = publish_protein_subtype_access_surface(request)
    assert result.request_digest == canonical_request_digest(request.model_dump(mode="json"))
    assert contract_json_schema("request")["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M26-04"
    assert _findings(request.model_copy(update={"audit_events": ()}))


def test_api_valid_schema_and_authorization_error_routes() -> None:
    client = TestClient(api.create_app())
    schema = client.get("/v1/modules/M26-04/schemas/request")
    assert schema.status_code == HTTPStatus.OK
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    denied = client.post(
        "/v1/modules/M26-04/publish",
        content=request.model_copy(update={"context": context}).model_dump_json(),
    )
    assert denied.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "rejected" not in denied.text


def test_api_validate_sanitizes_authorization_failure() -> None:
    client = TestClient(api.create_app())
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    response = client.post(
        "/v1/modules/M26-04/validate",
        content=request.model_copy(update={"context": context}).model_dump_json(),
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "rejected" not in response.text


def test_api_wrapped_verify_and_sdk_json_facade() -> None:
    request = _request()
    client = TestClient(api.create_app())
    published = client.post("/v1/modules/M26-04/publish", content=request.model_dump_json())
    wrapped = client.post("/v1/modules/M26-04/verify", json={"result": published.json()})
    assert wrapped.status_code == HTTPStatus.OK
    assert wrapped.json()["verified"] is True
    sdk_result = M2604Plugin().replay(published.json())
    assert sdk_result.result_id == published.json()["result_id"]


def test_cli_schema_stdout_abstention_exit_and_replay_error(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    request = _request()
    denied = request.authorizations[0].model_copy(update={"decision": AuthorizationDecision.DENY})
    request_path = tmp_path / "denied.json"
    output_path = tmp_path / "denied-result.json"
    request_path.write_text(
        request.model_copy(update={"authorizations": (denied,)}).model_dump_json(),
        encoding="utf-8",
    )
    abstained = runner.invoke(cli.app, ["publish", str(request_path), "--output", str(output_path)])
    assert abstained.exit_code == 1
    assert output_path.exists()
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    verify = runner.invoke(cli.app, ["verify", str(bad_result)])
    assert verify.exit_code != 0


def test_service_typed_replay_and_sdk_json_publish() -> None:
    request = _request()
    service = M2604Service()
    result = service.publish(request)
    assert service.replay(result).result_digest == result.result_digest
    assert M2604Client(service).publish_json(request)["result_id"] == result.result_id
    job = request.jobs[0]
    with pytest.raises(ValidationError, match="non-success async job"):
        AsyncJobRecord.model_validate(
            job.model_copy(update={"status": JobStatus.CANCELLED}).model_dump(mode="python")
        )


def test_service_descriptor_and_plugin_capability_seals_are_closed() -> None:
    request = _request()
    service = M2604Service()
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M26-04"
    plugin = M2604Plugin(service)
    other = M2604Plugin(service)
    token = plugin.validate(GatewaySubmission(request))
    with pytest.raises(M2604TokenError):
        other.run(token)
    token._seal = object()
    with pytest.raises(M2604TokenError):
        plugin.run(token)


def test_cli_publish_stdout_and_api_schema_boundary(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["publish", str(request_path)])
    assert result.exit_code == 0
    assert '"status":"published"' in result.stdout


def test_incompatible_and_migration_rules_never_publish() -> None:
    request = _request()
    for status in (CompatibilityStatus.INCOMPATIBLE, CompatibilityStatus.MIGRATION_REQUIRED):
        rule = request.compatibility_rules[0].model_copy(update={"status": status})
        result = M2604GatewayEngine().publish(
            request.model_copy(update={"compatibility_rules": (rule,)})
        )
        assert result.status.value == "abstained"
        assert result.support_decision.status.value == "review_required"


def test_api_malformed_and_tampered_envelopes_are_sanitized() -> None:
    client = TestClient(api.create_app())
    malformed = client.post(
        "/v1/modules/M26-04/publish",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not-json" not in malformed.text
    result = M2604GatewayEngine().publish(_request()).model_dump(mode="json")
    result["result_id"] = "m2604.forged"
    tampered = client.post("/v1/modules/M26-04/verify", json=result)
    assert tampered.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "m2604.forged" not in tampered.text


def test_cli_rejects_duplicate_json_and_preserves_existing_output(tmp_path: Path) -> None:
    runner = CliRunner()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"request_id":"one","request_id":"two"}', encoding="utf-8")
    invalid = runner.invoke(cli.app, ["validate", str(duplicate)])
    assert invalid.exit_code != 0
    assert "two" not in invalid.output
    output = tmp_path / "existing.json"
    output.write_text("sentinel", encoding="utf-8")
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    overwrite = runner.invoke(cli.app, ["publish", str(request_path), "--output", str(output)])
    assert overwrite.exit_code != 0
    assert output.read_text(encoding="utf-8") == "sentinel"


def test_mapping_service_and_plugin_reject_non_object_json() -> None:
    service = M2604Service()
    with pytest.raises(M2604AuthorizationError):
        service.validate_request("[]")
    plugin = M2604Plugin(service)
    with pytest.raises(ValidationError, match="object"):
        plugin.validate(GatewaySubmission("[]"))


def test_authorization_denial_does_not_leak_surface() -> None:
    request = _request()
    denial = request.authorizations[0].model_copy(
        update={"decision": AuthorizationDecision.REVIEW_REQUIRED}
    )
    result = M2604GatewayEngine().publish(request.model_copy(update={"authorizations": (denial,)}))
    assert result.access_surface is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_operation_protocol_mismatch_is_contract_error() -> None:
    request = _request()
    operation = request.operations[0].model_copy(update={"protocol": AccessProtocol.CLI})
    configuration = request.configuration.model_copy(
        update={"supported_protocols": (AccessProtocol.API,)}
    )
    with pytest.raises(ValidationError, match="operation protocol"):
        AccessSurface(
            surface_id="m2604.surface.protocol",
            version="1.0.0",
            operations=(operation,),
            authorizations=request.authorizations,
            idempotency_records=request.idempotency_records,
            jobs=request.jobs,
            compatibility_rules=request.compatibility_rules,
            errors=request.errors,
            audit_events=request.audit_events,
            configuration=configuration,
            evidence=request.operations[0].evidence,
        )
