"""Adversarial boundary and replay tests for M26-01."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_01 import (
    ActiveConfiguration,
    RegistryEntryStatus,
    RegistryRecord,
    RegistryStatus,
    canonical_request_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    M2601AuthorizationError,
    M2601Plugin,
    M2601RegistryEngine,
    M2601ReplayError,
    M2601Service,
    M2601TokenError,
    RegistrySubmission,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    api as m2601_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    cli as m2601_cli,
)
from tests.contract.test_m2601_deep import _request

if TYPE_CHECKING:
    from pathlib import Path as PathType


def test_plugin_rejects_duplicate_json_keys_before_contract_parse() -> None:
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        M2601Plugin().validate(RegistrySubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_submission_and_forged_token() -> None:
    plugin = M2601Plugin()
    with pytest.raises(M2601TokenError):
        plugin.validate(_request())  # type: ignore[arg-type]
    with pytest.raises(M2601TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_service_fails_closed_on_unknown_and_hostile_control_mappings() -> None:
    with pytest.raises(M2601AuthorizationError):
        M2601Service().validate_request({"context": {"references": {}}})

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError from None

    with pytest.raises(M2601AuthorizationError):
        M2601Service().validate_request(BrokenMapping())


def test_contract_rejects_unknown_history_entry_and_context_mismatch() -> None:
    request = _request()
    foreign_event = request.history[0].model_copy(update={"entry_id": "m2601.entry.foreign"})
    payload = request.model_dump(mode="python")
    payload["history"] = (foreign_event, *request.history[1:])
    with pytest.raises(ValidationError, match="unknown entry"):
        type(request).model_validate(payload)
    mismatch = request.model_copy(
        update={"context": request.context.model_copy(update={"request_id": "m2601.other"})}
    )
    with pytest.raises(ValidationError, match="context request ID"):
        type(request).model_validate(mismatch)


def test_contract_rejects_configuration_kind_or_entry_mismatch() -> None:
    request = _request()
    binding = request.active_configuration.bindings[0].model_copy(
        update={"entry_id": request.entries[1].entry_id}
    )
    configuration = request.active_configuration.model_copy(
        update={"bindings": (binding, *request.active_configuration.bindings[1:])}
    )
    with pytest.raises(ValidationError, match="kind does not match"):
        type(request).model_validate(
            request.model_copy(update={"active_configuration": configuration})
        )


def test_contract_rejects_duplicate_configuration_ids_and_history_events() -> None:
    request = _request()
    binding = request.active_configuration.bindings[0].model_copy(
        update={"binding_id": request.active_configuration.bindings[1].binding_id}
    )
    with pytest.raises(ValidationError, match="binding ids"):
        ActiveConfiguration.model_validate(
            request.active_configuration.model_copy(
                update={"bindings": (binding, *request.active_configuration.bindings[1:])}
            )
        )
    event = request.history[0].model_copy(update={"event_id": request.history[1].event_id})
    with pytest.raises(ValidationError, match="history event ids"):
        RegistryRecord(
            registry_id=request.registry_id,
            version=request.registry_version,
            entries=request.entries,
            history=(event, *request.history[1:]),
            lock_digest=sha256_digest(request.entries),
        )


def test_api_replay_rejects_nonobject_and_tampered_result() -> None:
    request = _request()
    client = TestClient(m2601_api.create_app())
    nonobject = client.post("/v1/modules/M26-01/verify", json=["not-an-object"])
    assert nonobject.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    result = client.post(
        "/v1/modules/M26-01/register",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    ).json()
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M26-01/verify", json=result)
    assert tampered.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "replay envelope" in tampered.text


def test_api_rejects_duplicate_keys_without_echoing_sensitive_payload() -> None:
    client = TestClient(m2601_api.create_app())
    response = client.post(
        "/v1/modules/M26-01/validate",
        content=b'{"request_id":"a","request_id":"sensitive-second"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "sensitive-second" not in response.text


def test_cli_unknown_schema_missing_input_and_bad_result_are_sanitized(
    tmp_path: PathType,
) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2601_cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    assert "unknown M26-01 contract" in unknown.output
    missing = runner.invoke(m2601_cli.app, ["validate", str(tmp_path / "missing.json")])
    assert missing.exit_code != 0
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    invalid = runner.invoke(m2601_cli.app, ["verify", str(bad)])
    assert invalid.exit_code != 0


def test_service_json_and_mapping_results_are_deterministic() -> None:
    request = _request()
    service = M2601Service()
    first = service.register(request.model_dump_json())
    second = service.register(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    assert first == second
    assert service.replay(first.model_dump(mode="json")) == first
    assert service.replay(first.model_dump_json()) == first


def test_plugin_descriptor_boundaries_and_model_submission() -> None:
    plugin = M2601Plugin()
    token = plugin.validate(RegistrySubmission(_request()))
    result = plugin.run(token)
    assert result.parent_target == "protein subtype"
    assert plugin.descriptor.immutable_history is True
    assert plugin.descriptor.active_configuration is True
    assert plugin.descriptor.unsupported_to_negative is False
    assert plugin.descriptor.kinase_activity is False
    assert plugin.descriptor.treatment_recommendation is False
    assert plugin.descriptor.identity_inference is False


def test_replay_checks_each_digest_and_expected_projection() -> None:
    engine = M2601RegistryEngine()
    result = engine.register(_request())
    cases = (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "registry.m2601.forged"}),
        result.model_copy(update={"result_digest": "sha256:" + "f" * 64}),
    )
    for candidate in cases:
        with pytest.raises(M2601ReplayError):
            engine.replay(candidate)

    other = _request(request_id="m2601.request.other")
    changed = result.model_copy(
        update={
            "request": other,
            "request_digest": canonical_request_digest(other),
            "result_id": result_identifier(canonical_request_digest(other)),
        }
    )
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(M2601ReplayError):
        engine.replay(changed)


def test_strict_result_validation_rejects_self_rehashed_registry_substitution() -> None:
    result = M2601RegistryEngine().register(_request())
    assert result.registry is not None
    altered_entry = result.registry.entries[0].model_copy(update={"owner": "forged-owner"})
    forged_registry = result.registry.model_copy(
        update={"entries": (altered_entry, *result.registry.entries[1:])}
    )
    forged = result.model_copy(update={"registry": forged_registry})
    payload = forged.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(payload)

    with pytest.raises(ValidationError, match="exact request material"):
        type(result).model_validate(payload, strict=True)


def test_result_abstention_and_registry_boundaries_remain_typed() -> None:
    request = _request()
    quarantined = request.entries[0].model_copy(update={"status": RegistryEntryStatus.QUARANTINED})
    result = M2601RegistryEngine().register(
        request.model_copy(update={"entries": (quarantined, *request.entries[1:])})
    )
    assert result.status is RegistryStatus.ABSTAINED
    assert result.registry is None
    assert result.active_configuration is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert canonical_request_digest(result.request) == result.request_digest


def test_superseded_entry_is_not_resolved_as_active() -> None:
    request = _request()
    superseded = request.entries[0].model_copy(update={"status": RegistryEntryStatus.SUPERSEDED})
    result = M2601RegistryEngine().register(
        request.model_copy(update={"entries": (superseded, *request.entries[1:])})
    )
    assert result.status is RegistryStatus.ABSTAINED
    assert any(item.code.value == "incompatible_configuration" for item in result.findings)


def test_replay_digest_identifier_and_projection_guards() -> None:
    engine = M2601RegistryEngine()
    result = engine.register(_request())
    for candidate in (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "registry.m2601.forged"}),
        result.model_copy(update={"result_digest": "sha256:" + "f" * 64}),
    ):
        with pytest.raises(M2601ReplayError):
            engine.replay(candidate)


def test_api_known_schema_and_denied_controls_are_sanitized() -> None:
    request = _request()
    denied_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_refs = request.context.references.model_copy(update={"support": denied_support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": denied_refs})}
    )
    client = TestClient(m2601_api.create_app())
    schema = client.get("/v1/modules/M26-01/schemas/request")
    assert schema.status_code == HTTPStatus.OK
    for route in ("validate", "register"):
        response = client.post(
            f"/v1/modules/M26-01/{route}",
            content=denied.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    malformed = client.post(
        "/v1/modules/M26-01/verify",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not-json" not in malformed.text


def test_cli_register_stdout_and_denied_request(tmp_path: PathType) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    output = CliRunner().invoke(m2601_cli.app, ["register", str(request_path)])
    assert output.exit_code == 0
    assert json.loads(output.stdout)["status"] == "registered"

    schema_path = tmp_path / "schema.json"
    exported = CliRunner().invoke(
        m2601_cli.app,
        ["export-schema", "request", "--output", str(schema_path)],
    )
    assert exported.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["title"]

    denied_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_refs = request.context.references.model_copy(update={"support": denied_support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": denied_refs})}
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(denied.model_dump_json(), encoding="utf-8")
    validation = CliRunner().invoke(m2601_cli.app, ["validate", str(denied_path)])
    assert validation.exit_code != 0
    denied_register = CliRunner().invoke(m2601_cli.app, ["register", str(denied_path)])
    assert denied_register.exit_code != 0


def test_plugin_public_validation_and_contract_result_closure() -> None:
    plugin = M2601Plugin()
    request = _request()
    assert plugin.validate_request(request) == request

    engine = M2601RegistryEngine()
    result = engine.register(request)
    missing_registry = result.model_copy(update={"registry": None})
    with pytest.raises(ValidationError, match="registered result"):
        type(result).model_validate(missing_registry.model_dump(mode="python"))
    abstained = result.model_copy(
        update={
            "status": RegistryStatus.ABSTAINED,
            "registry": None,
            "active_configuration": None,
            "abstention_reason": None,
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            ),
        }
    )
    abstained = abstained.model_copy(update={"result_digest": result_payload_digest(abstained)})
    with pytest.raises(ValidationError, match="abstained result"):
        type(result).model_validate(abstained.model_dump(mode="python"))
