"""Deep adversarial and boundary coverage for M20-07."""

from __future__ import annotations

import json
from typing import Any

import pytest
from evals.m20_07.benchmark import main as benchmark_main
from evals.m20_07.run import main as evaluator_main
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m20_07 import ExportStatus, result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m20_07_downstream_typed_export import (
    M2007AuthorizationError,
    M2007Engine,
    M2007ExportError,
    M2007Plugin,
    M2007ReplayError,
    cli_app,
    create_app,
    export_protein_subtype_downstream_contract,
)
from glio_proteogen.modules.c20_biomarker_panel.m20_07_downstream_typed_export import (
    engine as engine_module,
)
from tests.contract.test_m20_07_hardening import _field, _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_preflight_rejects_malformed_and_missing_control_objects() -> None:
    class BrokenContext:
        @property
        def references(self) -> object:
            raise RuntimeError("malformed")

    with pytest.raises(M2007AuthorizationError):
        M2007Engine().export({"context": BrokenContext()})
    with pytest.raises(M2007AuthorizationError):
        M2007Engine().export({"context": {"references": {}}})


def test_api_sanitizes_unknown_schema_non_object_and_denial() -> None:
    request = _request()
    client = TestClient(create_app())
    assert client.get("/v1/modules/M20-07/schemas/unknown").status_code == _HTTP_NOT_FOUND
    invalid = client.post("/v1/modules/M20-07/validate", content=b"[]")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid.text
    assert (
        client.post("/v1/modules/M20-07/verify", content=b"not-json").status_code
        == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post("/v1/modules/M20-07/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    denied = request.model_copy(
        update={
            "consent": request.consent.model_copy(update={"state": ConsentState.WITHHELD}),
        }
    )
    response = client.post("/v1/modules/M20-07/export", json=denied.model_dump(mode="json"))
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == ExportStatus.ABSTAINED.value
    context_withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied_context = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": context_withheld}
                    )
                }
            )
        }
    )
    assert (
        client.post(
            "/v1/modules/M20-07/validate", json=denied_context.model_dump(mode="json")
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post(
            "/v1/modules/M20-07/export", json=denied_context.model_dump(mode="json")
        ).status_code
        == _HTTP_UNPROCESSABLE
    )


def test_cli_rejects_bad_input_and_refuses_overwrite(tmp_path: Any) -> None:
    runner = CliRunner()
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code != 0
    assert runner.invoke(cli_app, ["export", str(bad)]).exit_code != 0
    assert runner.invoke(cli_app, ["verify", str(bad)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    schema = tmp_path / "schema.json"
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema)]).exit_code == 0
    )
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema)]).exit_code != 0
    )


def test_plugin_rejects_malformed_json_and_unsealed_tokens() -> None:
    plugin = M2007Plugin()
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(b"[]")
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(b'{"request_id":"missing"}')
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    assert plugin.run(plugin.validate(_request())).status is ExportStatus.EXPORTED


def test_export_rejects_granted_consent_not_bound_to_context() -> None:
    request = _request()
    forged = request.model_copy(
        update={"consent": request.consent.model_copy(update={"decision_id": "decision.foreign"})}
    )
    with pytest.raises(M2007ExportError, match="request is invalid"):
        M2007Engine().export(forged)


def test_provenance_covers_nested_export_evidence() -> None:
    request = _request()
    result = M2007Engine().export(request)
    nested_digests = {
        request.consent.evidence.digest,
        *(item.reference.digest for item in request.configuration.evidence),
        *(item.reference.digest for field in request.fields for item in field.evidence),
    }

    assert nested_digests <= set(result.provenance.input_digests)


def test_tampered_contract_and_payload_never_replay() -> None:
    engine = M2007Engine()
    result = engine.export(_request())
    assert result.contract is not None
    tampered = result.model_copy(
        update={
            "contract": result.contract.model_copy(
                update={
                    "ownership": result.contract.ownership.model_copy(update={"owner": "tampered"})
                }
            )
        }
    )
    with pytest.raises(M2007ReplayError):
        engine.verify(tampered, replay=False)
    replay_tampered = result.model_copy(update={"human_review_required": True})
    replay_tampered = replay_tampered.model_copy(
        update={"result_digest": result_payload_digest(replay_tampered)}
    )
    with pytest.raises(M2007ReplayError):
        engine.verify(replay_tampered)


def test_unsupported_and_negative_claim_text_abstain() -> None:
    request = _request().model_copy(
        update={
            "fields": (
                _field().model_copy(update={"documentation": "unsupported negative finding"}),
            ),
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="supported",
                rationale="Support is declared, but text is outside the boundary.",
            ),
        }
    )
    result = M2007Engine().export(request)
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.abstention_reason is not None


def test_public_entrypoints_and_json_parity() -> None:
    request = _request()
    plugin = M2007Plugin()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
    assert plugin.run(plugin.validate(encoded)).model_dump(mode="json") == M2007Engine().export(
        request
    ).model_dump(mode="json")
    assert benchmark_main([]) == 0
    assert evaluator_main([]) == 0
    assert export_protein_subtype_downstream_contract(request) == M2007Engine().export(request)


def test_validation_and_result_construction_fail_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    malformed = request.model_dump(mode="python")
    malformed.pop("fields")
    with pytest.raises(M2007ExportError, match="request is invalid"):
        M2007Engine().validate_request(malformed)

    monkeypatch.setattr(engine_module, "result_payload_digest", lambda _: "sha256:" + "f" * 64)
    with pytest.raises(M2007ExportError, match="construction failed safely"):
        M2007Engine().export(request)


def test_cli_round_trip_uses_canonical_bytes(tmp_path: Any) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    runner = CliRunner()
    assert (
        runner.invoke(
            cli_app, ["export", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
