"""Adversarial closure for M27-04 boundaries and safe abstention."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glio_proteogen.contracts.m27_04 import (
    AccessProtocol,
    AsyncJobRecord,
    CompatibilityStatus,
    ComplexActivityAccessSurfaceResult,
    GatewayConfiguration,
    GatewayFindingCode,
    GatewayStatus,
    JobStatus,
    OperationStatus,
    PublishComplexActivityAccessSurfaceRequest,
)
from glio_proteogen.contracts.m27_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway import api
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.engine import (
    M2704GatewayEngine,
    M2704ReplayError,
    _validate_request,
    preflight_m2704_authorization,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.plugin import (
    GatewaySubmission,
    M2704Plugin,
    M2704TokenError,
)
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.service import (
    M2704Service,
)
from tests.runtime.test_m2704_runtime import _evidence, _request


def test_mapping_and_json_inputs_preserve_one_canonical_result() -> None:
    request = _request()
    engine = M2704GatewayEngine()
    typed = engine.publish(request)
    mapping = engine.publish(request.model_dump(mode="json"))
    encoded = M2704Service().publish(request.model_dump_json())
    assert mapping == typed
    assert encoded == typed


def test_hostile_preflight_objects_fail_closed_without_traversal() -> None:
    with pytest.raises(ValueError, match="requires accepted configuration"):
        preflight_m2704_authorization({"context": {"references": object()}})


def test_disabled_operation_abstains_and_keeps_typed_finding() -> None:
    request = _request()
    operation = request.operations[0].model_copy(update={"status": OperationStatus.DISABLED})
    result = M2704GatewayEngine().publish(request.model_copy(update={"operations": (operation,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert any(item.code is GatewayFindingCode.OPERATION_UNAUTHORIZED for item in result.findings)


def test_unresolved_compatibility_abstains_without_negative_claim() -> None:
    request = _request()
    rule = request.compatibility_rules[0].model_copy(
        update={"status": CompatibilityStatus.MIGRATION_REQUIRED}
    )
    result = M2704GatewayEngine().publish(
        request.model_copy(update={"compatibility_rules": (rule,)})
    )
    assert result.status is GatewayStatus.ABSTAINED
    assert result.access_surface is None
    assert result.support_decision.status.value == "review_required"


def test_plugin_rejects_foreign_and_forged_capabilities() -> None:
    request = _request()
    first = M2704Plugin()
    second = M2704Plugin()
    token = first.validate(GatewaySubmission(request.model_dump_json()))
    with pytest.raises(M2704TokenError):
        second.run(token)
    with pytest.raises(M2704TokenError):
        first.run(object())  # type: ignore[arg-type]


def test_plugin_token_rejects_post_issuance_request_replacement() -> None:
    request = _request()
    plugin = M2704Plugin()
    token = plugin.validate(GatewaySubmission(request))
    object.__setattr__(token, "request", request.model_copy(deep=True))
    with pytest.raises(M2704TokenError):
        plugin.run(token)


def test_service_rejects_duplicate_keys_and_unknown_payload_fields() -> None:
    service = M2704Service()
    with pytest.raises((StrictJsonError, ValueError, ValidationError)):
        service.publish(b'{"request_id":"first","request_id":"second"}')
    payload = _request().model_dump(mode="json")
    payload["untrusted_claim"] = "not accepted"
    with pytest.raises((ValueError, ValidationError)):
        service.publish(payload)


def test_replay_rejects_forged_payload_and_plugin_metadata_is_closed() -> None:
    request = _request()
    result = M2704GatewayEngine().publish(request)
    forged = result.model_copy(update={"request_digest": "sha256:" + "0" * 64})
    with pytest.raises(M2704ReplayError):
        M2704GatewayEngine().replay(forged)
    descriptor = M2704Plugin.descriptor
    assert descriptor.provisional_abi is True
    assert descriptor.unsupported_to_negative is False
    assert descriptor.kinase_activity is False
    assert descriptor.all_omics_fusion is False
    assert descriptor.treatment_recommendation is False
    assert descriptor.identity_inference is False
    assert descriptor.consent_inference is False


def test_api_replay_uses_result_size_ceiling_not_request_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    result = M2704GatewayEngine().publish(request).model_dump(mode="json")
    body = canonical_json_bytes({"result": result})
    monkeypatch.setattr(api, "M2704_MAX_CANONICAL_REQUEST_BYTES", len(body) - 1)
    monkeypatch.setattr(api, "M2704_MAX_CANONICAL_RESULT_BYTES", len(body))

    with TestClient(api.create_app()) as client:
        verified = client.post(
            "/v1/modules/M27-04/verify",
            content=body,
            headers={"content-type": "application/json"},
        )

    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_contract_rejects_invalid_terminal_job_outcomes() -> None:
    request = _request()
    idempotency = request.idempotency_records[0]
    evidence = (_evidence(),)
    with pytest.raises(ValueError, match="requires a result artifact"):
        AsyncJobRecord(
            job_id="m2704.invalid.succeeded",
            operation_id=idempotency.operation_id,
            status=JobStatus.SUCCEEDED,
            idempotency=idempotency,
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="cannot carry a result artifact"):
        AsyncJobRecord(
            job_id="m2704.invalid.abstained",
            operation_id=idempotency.operation_id,
            status=JobStatus.ABSTAINED,
            idempotency=idempotency,
            result_artifact=request.source_artifacts[0],
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="requires a typed error code"):
        AsyncJobRecord(
            job_id="m2704.invalid.failed",
            operation_id=idempotency.operation_id,
            status=JobStatus.FAILED,
            idempotency=idempotency,
            evidence=evidence,
        )


def test_contract_rejects_duplicate_protocols_and_source_identity() -> None:
    evidence = (_evidence(),)
    with pytest.raises(ValueError, match="protocols must be unique"):
        GatewayConfiguration(
            configuration_id="m2704.invalid.configuration",
            version="1.0.0",
            supported_protocols=(AccessProtocol.API, AccessProtocol.API),
            evidence=evidence,
        )
    request = _request()
    with pytest.raises(ValueError, match="source artifact ids must be unique"):
        PublishComplexActivityAccessSurfaceRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "source_artifacts": (request.source_artifacts[0], request.source_artifacts[0]),
            },
            strict=True,
        )
    duplicate_digest = request.source_artifacts[1].model_copy(
        update={"digest": request.source_artifacts[0].digest}
    )
    with pytest.raises(ValueError, match="source artifact digests must be unique"):
        PublishComplexActivityAccessSurfaceRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "source_artifacts": (request.source_artifacts[0], duplicate_digest),
            },
            strict=True,
        )


def test_contract_rejects_unresolved_graph_references() -> None:
    request = _request()
    authorization = request.authorizations[0].model_copy(update={"operation_id": "unknown"})
    with pytest.raises(ValueError, match="unknown operation"):
        PublishComplexActivityAccessSurfaceRequest.model_validate(
            {**request.model_dump(mode="python"), "authorizations": (authorization,)},
            strict=True,
        )
    configuration = request.configuration.model_copy(
        update={"supported_protocols": (AccessProtocol.SDK,)}
    )
    with pytest.raises(ValueError, match="protocol is not enabled"):
        PublishComplexActivityAccessSurfaceRequest.model_validate(
            {**request.model_dump(mode="python"), "configuration": configuration},
            strict=True,
        )


def test_canonical_dict_projection_and_engine_parse_paths() -> None:
    request = _request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert _validate_request(request.model_dump_json()) == request
    assert _validate_request(request.model_dump(mode="json")) == request


def test_preflight_property_errors_fail_closed() -> None:
    class ExplodingContext:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile context")  # noqa: TRY003

    with pytest.raises(ValueError, match="requires accepted configuration"):
        preflight_m2704_authorization(ExplodingContext())


def test_plugin_and_sdk_passthrough_edges_are_exercised() -> None:
    request = _request()
    plugin = M2704Plugin()
    with pytest.raises(M2704TokenError):
        plugin.validate(object())  # type: ignore[arg-type]
    assert plugin.validate_request(request) == request
    result = plugin.run(plugin.validate(GatewaySubmission(request)))
    assert plugin.replay(result) == result
    assert M2704Service().descriptor["module_id"] == "GLIO-PROTEOGEN-M27-04"


def test_replay_checks_each_digest_and_identifier_binding() -> None:
    request = _request()
    engine = M2704GatewayEngine()
    result = engine.publish(request)
    for field, value in (
        ("request_digest", "sha256:" + "0" * 64),
        ("result_id", "gateway.m2704.forged"),
        ("result_digest", "sha256:" + "1" * 64),
    ):
        forged = result.model_copy(update={field: value})
        with pytest.raises(M2704ReplayError):
            engine.replay(forged)


@pytest.mark.parametrize(
    "field", ["surface_id", "operations", "authorizations", "configuration", "evidence"]
)
def test_result_contract_rejects_self_rehashed_surface_forgery(field: str) -> None:
    request = _request()
    result = M2704GatewayEngine().publish(request)
    assert result.access_surface is not None
    surface = result.access_surface
    if field == "surface_id":
        forged_surface = surface.model_copy(update={"surface_id": "m2704.surface.forged"})
    elif field == "operations":
        operation = surface.operations[0].model_copy(update={"name": "forged operation"})
        forged_surface = surface.model_copy(
            update={"operations": (operation, *surface.operations[1:])}
        )
    elif field == "authorizations":
        authorization = surface.authorizations[0].model_copy(
            update={"principal_id": "principal:forged"}
        )
        forged_surface = surface.model_copy(
            update={"authorizations": (authorization, *surface.authorizations[1:])}
        )
    elif field == "configuration":
        configuration = surface.configuration.model_copy(update={"version": "9.9.9"})
        forged_surface = surface.model_copy(update={"configuration": configuration})
    else:
        evidence = surface.evidence[0].model_copy(update={"claim": "forged evidence"})
        forged_surface = surface.model_copy(update={"evidence": (evidence, *surface.evidence[1:])})
    forged = result.model_copy(update={"access_surface": forged_surface})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="published result"):
        ComplexActivityAccessSurfaceResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )


@pytest.mark.parametrize(
    "field",
    ["activity_id", "actor_id", "input_digests", "configuration_digest", "control_decisions"],
)
def test_result_contract_rejects_self_rehashed_provenance_forgery(field: str) -> None:
    result = M2704GatewayEngine().publish(_request())
    forged_values = {
        "activity_id": "m2704.activity.forged",
        "actor_id": "actor:forged",
        "input_digests": ("sha256:" + "f" * 64,),
        "configuration_digest": "sha256:" + "e" * 64,
        "control_decisions": (
            result.provenance.control_decisions[0].model_copy(
                update={"decision_id": "control:forged"}
            ),
            *result.provenance.control_decisions[1:],
        ),
    }
    forged_provenance = result.provenance.model_copy(update={field: forged_values[field]})
    forged = result.model_copy(update={"provenance": forged_provenance})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match="gateway provenance"):
        ComplexActivityAccessSurfaceResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )
