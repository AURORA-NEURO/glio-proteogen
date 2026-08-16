"""Adversarial contract, runtime, plugin, API, and CLI coverage for M17-07."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m17_07.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.m1707 import cli, create_app
from glio_proteogen.contracts.m17_07 import (
    M1707_M1706_INPUT_MEDIA_TYPE,
    CompatibilityMode,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportFieldType,
    ExportStatus,
    VariantPeptideDownstreamExportResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_07_downstream_typed_export import (
    M1707AuthorizationError,
    M1707DownstreamTypedExportEngine,
    M1707Plugin,
    M1707ReplayVerificationError,
    M1707Service,
    ValidatedM1707Request,
    preflight_m1707_authorization,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_07_downstream_typed_export.engine import (
    _classify,
)

if TYPE_CHECKING:
    from pathlib import Path


HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
CLI_ERROR = 1
CLI_REFUSED = 2
SEVEN_CONTROLS = 7
ESTIMATED_PROBABILITY = 0.9


def _request_payload(request: object) -> dict[str, object]:
    return request.model_dump(mode="json")  # type: ignore[union-attr]


def _validated_request(request: object, **updates: object) -> object:
    payload = request.model_dump(mode="python")  # type: ignore[union-attr]
    payload.update(updates)
    return type(request).model_validate(payload, strict=True)


def test_runtime_exports_closed_contract_with_seven_uncertainty_dimensions() -> None:
    request = build_scenario_request()
    result = M1707DownstreamTypedExportEngine().infer(request)

    assert result.status is ExportStatus.EXPORTED
    assert result.contract is not None
    assert result.contract.parent_target == "variant peptide"
    assert result.emits_parent is False
    assert result.contract.signature.signed_payload_digest.startswith("sha256:")
    assert result.uncertainty.measurement.probability == ESTIMATED_PROBABILITY
    assert result.uncertainty.transport.probability == ESTIMATED_PROBABILITY
    assert len(result.provenance.control_decisions) == SEVEN_CONTROLS
    assert result.findings[0].code.value == "provisional_abi_pending_review"


@pytest.mark.parametrize(
    ("scenario", "finding"),
    [
        ("unsupported", "support_boundary"),
        ("compatibility", "compatibility_mismatch"),
    ],
)
def test_runtime_abstains_without_contract_and_exposes_safe_status(
    scenario: str, finding: str
) -> None:
    result = M1707DownstreamTypedExportEngine().infer(build_scenario_request(scenario))

    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.abstention_reason
    assert finding in {item.code.value for item in result.findings}
    assert result.uncertainty.measurement.probability is None
    assert any(item.code == "safe_abstention" for item in result.limitations)


def test_service_accepts_canonical_bytes_and_mapping_but_rejects_duplicate_json() -> None:
    service = M1707Service()
    request = build_scenario_request()
    payload = canonical_json_bytes(request)
    assert service.execute(payload) == service.execute(_request_payload(request))

    with pytest.raises(ValueError, match="duplicate"):
        service.execute(b'{"request_id":"first","request_id":"second"}')


def test_service_verify_accepts_bytes_mapping_and_typed_result() -> None:
    service = M1707Service()
    result = service.execute(build_scenario_request())
    assert service.verify(canonical_json_bytes(result)) == result
    assert service.verify(result.model_dump(mode="json")) == result
    assert service.verify(result) == result
    assert service.verify(result, replay=False) == result


def test_plugin_requires_issued_parse_once_token_and_preserves_descriptor() -> None:
    service = M1707Service()
    plugin = M1707Plugin(service)
    request = build_scenario_request()
    token = plugin.validate(canonical_json_bytes(request))
    assert isinstance(token, ValidatedM1707Request)
    assert plugin.run(token).status is ExportStatus.EXPORTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M17-07"

    forged = ValidatedM1707Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_rejects_mutated_token_snapshot() -> None:
    plugin = M1707Plugin(M1707Service())
    token = plugin.validate(build_scenario_request())
    object.__setattr__(token, "request", build_scenario_request("unsupported"))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_authorization_preflight_is_fail_closed_for_identity_and_consent() -> None:
    engine = M1707DownstreamTypedExportEngine()
    request = build_scenario_request()
    references = request.context.references
    denied_identity = references.identity_lineage.model_copy(update={"state": "conflicted"})
    denied_context = request.context.model_copy(
        update={"references": references.model_copy(update={"identity_lineage": denied_identity})}
    )
    with pytest.raises(M1707AuthorizationError):
        engine.infer(request.model_copy(update={"context": denied_context}))

    withheld = request.model_copy(
        update={"consent": request.consent.model_copy(update={"state": ConsentState.WITHHELD})}
    )
    with pytest.raises(ValidationError, match="bind the caller-declared consent"):
        engine.infer(withheld)


def test_authorization_supports_mapping_inputs_and_rejects_broken_context() -> None:
    states = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    preflight_m1707_authorization(
        {"context": {"references": {role: {"state": state} for role, state in states.items()}}}
    )

    class BrokenMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(M1707AuthorizationError):
        preflight_m1707_authorization({"context": BrokenMapping()})


def test_classification_records_withheld_consent_without_authorization_traversal() -> None:
    request = build_scenario_request().model_copy(
        update={
            "consent": build_scenario_request().consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    status, findings = _classify(request)
    assert status is ExportStatus.ABSTAINED
    assert findings[0].value == "consent_withheld"


def test_contract_rejects_wrong_upstream_media_and_unbound_field() -> None:
    request = build_scenario_request()
    bad_adjudication = request.adjudication_result.model_copy(
        update={"media_type": "application/octet-stream"}
    )
    with pytest.raises(ValidationError, match="M17-06 adjudication"):
        _validated_request(request, adjudication_result=bad_adjudication)

    field = request.fields[0].model_copy(update={"value_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="field value"):
        _validated_request(request, fields=(field, *request.fields[1:]))


def test_contract_rejects_duplicate_fields_and_source_artifacts() -> None:
    request = build_scenario_request()
    duplicate_field = request.fields[0].model_copy(update={"field_id": request.fields[1].field_id})
    with pytest.raises(ValidationError, match="field ids"):
        _validated_request(request, fields=(duplicate_field, *request.fields[1:]))

    with pytest.raises(ValidationError, match="source artifacts"):
        _validated_request(request, source_artifacts=(request.source_artifacts[0],) * 2)


def test_request_closure_rejects_duplicate_names_consent_drift_and_missing_bindings() -> None:
    request = build_scenario_request()
    duplicate_name = request.fields[0].model_copy(
        update={"field_name": request.fields[1].field_name}
    )
    with pytest.raises(ValidationError, match="field names"):
        _validated_request(request, fields=(duplicate_name, *request.fields[1:]))

    drifted_consent = request.consent.model_copy(update={"decision_id": "decision.other"})
    with pytest.raises(ValidationError, match="caller-declared consent"):
        _validated_request(request, consent=drifted_consent)

    with pytest.raises(ValidationError, match="adjudication result"):
        _validated_request(request, source_artifacts=request.source_artifacts[1:])

    field_evidence = (
        request.fields[0]
        .evidence[0]
        .model_copy(
            update={
                "reference": request.fields[0]
                .evidence[0]
                .reference.model_copy(update={"digest": "sha256:" + "f" * 64})
            }
        )
    )
    changed_field = request.fields[0].model_copy(update={"evidence": (field_evidence,)})
    with pytest.raises(ValidationError, match="field evidence"):
        _validated_request(request, fields=(changed_field, *request.fields[1:]))


def test_contract_closure_rejects_each_ownership_consent_signature_and_evidence_drift() -> None:
    result = M1707DownstreamTypedExportEngine().infer(build_scenario_request())
    assert result.contract is not None
    contract = result.contract

    def validate(candidate: DownstreamContractObject) -> None:
        DownstreamContractObject.model_validate(candidate.model_dump(mode="python"), strict=True)

    duplicate_id = contract.model_copy(
        update={
            "fields": (
                contract.fields[0],
                contract.fields[0].model_copy(update={"field_id": contract.fields[0].field_id}),
            )
        }
    )
    with pytest.raises(ValidationError, match="field ids"):
        validate(duplicate_id)

    duplicate_name = contract.model_copy(
        update={
            "fields": (
                contract.fields[0],
                contract.fields[1].model_copy(update={"field_name": contract.fields[0].field_name}),
                contract.fields[2],
            )
        }
    )
    with pytest.raises(ValidationError, match="field names"):
        validate(duplicate_name)

    with pytest.raises(ValidationError, match="granted consent"):
        validate(
            contract.model_copy(
                update={
                    "consent": contract.consent.model_copy(update={"state": ConsentState.WITHHELD})
                }
            )
        )
    with pytest.raises(ValidationError, match="supported status"):
        validate(
            contract.model_copy(
                update={
                    "support_decision": contract.support_decision.model_copy(
                        update={"status": SupportStatus.REVIEW_REQUIRED}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="ownership"):
        validate(
            contract.model_copy(
                update={
                    "ownership": contract.ownership.model_copy(
                        update={"owning_module": "GLIO-PROTEOGEN-OTHER"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="parent_target"):
        validate(
            contract.model_copy(
                update={
                    "configuration": contract.configuration.model_copy(
                        update={"parent_target": "other"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="payload digest"):
        validate(
            contract.model_copy(
                update={
                    "signature": contract.signature.model_copy(
                        update={"signed_payload_digest": "sha256:" + "0" * 64}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="every field evidence"):
        validate(contract.model_copy(update={"evidence": contract.evidence[:1]}))


def test_result_closure_rejects_digest_status_and_finding_drift() -> None:
    engine = M1707DownstreamTypedExportEngine()
    exported = engine.infer(build_scenario_request())
    abstained = engine.infer(build_scenario_request("unsupported"))

    def validate(result: VariantPeptideDownstreamExportResult) -> None:
        VariantPeptideDownstreamExportResult.model_validate(
            result.model_dump(mode="python"), strict=True
        )

    with pytest.raises(ValidationError, match="request digest"):
        validate(exported.model_copy(update={"request_digest": "sha256:" + "a" * 64}))
    with pytest.raises(ValidationError, match="exported result"):
        validate(exported.model_copy(update={"contract": None}))
    with pytest.raises(ValidationError, match="abstained result"):
        validate(abstained.model_copy(update={"contract": exported.contract}))
    with pytest.raises(ValidationError, match="abstained result"):
        validate(abstained.model_copy(update={"abstention_reason": None}))

    finding = exported.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        validate(exported.model_copy(update={"findings": (finding, finding)}))
    same_code = finding.model_copy(update={"finding_id": "finding.other"})
    with pytest.raises(ValidationError, match="finding codes"):
        validate(exported.model_copy(update={"findings": (finding, same_code)}))
    with pytest.raises(ValidationError, match="result digest"):
        validate(exported.model_copy(update={"result_digest": "sha256:" + "b" * 64}))


def test_canonical_dict_projection_and_engine_public_wrapper() -> None:
    request = build_scenario_request()
    assert canonical_request_digest(request.model_dump(mode="json")) == canonical_request_digest(
        request
    )


def test_replay_and_tamper_closure_is_canonical() -> None:
    engine = M1707DownstreamTypedExportEngine()
    result = engine.infer(build_scenario_request())
    assert engine.verify(result) == result
    assert engine.verify(result, replay=False) == result

    tampered = result.model_copy(update={"result_digest": "sha256:" + "a" * 64})
    with pytest.raises(M1707ReplayVerificationError):
        engine.verify(tampered)
    with pytest.raises(M1707ReplayVerificationError):
        engine.verify({"not": "a result"})


def test_api_schema_export_success_and_unknown_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/m17-07/schema/request")
        assert response.status_code == HTTP_OK
        assert response.json()["x-glio-contract"]["parentTarget"] == "variant peptide"
        missing = client.get("/v1/m17-07/schema/unknown")
        assert missing.status_code == HTTP_NOT_FOUND


def test_api_export_verify_parity_and_sanitized_failures() -> None:
    request = build_scenario_request()
    with TestClient(create_app()) as client:
        exported = client.post("/v1/modules/M17-07/export", json=_request_payload(request))
        assert exported.status_code == HTTP_OK
        body = exported.json()
        assert body["status"] == "exported"
        verified = client.post("/v1/modules/M17-07/verify", json=body)
        assert verified.status_code == HTTP_OK
        assert verified.json()["result_digest"] == body["result_digest"]

        denied = build_scenario_request(accepted=False)
        rejected = client.post("/v1/modules/M17-07/export", json=_request_payload(denied))
        assert rejected.status_code == HTTP_FORBIDDEN
        assert "requires accepted controls" not in rejected.text

        malformed = client.post("/v1/modules/M17-07/export", content=b"{not-json")
        assert malformed.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert "Traceback" not in malformed.text

        tampered = dict(body)
        tampered["result_digest"] = "sha256:" + "a" * 64
        replay = client.post("/v1/modules/M17-07/verify", json=tampered)
        assert replay.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_api_maps_explicit_replay_error_to_generic_422() -> None:
    class ReplayService(M1707Service):
        def verify(
            self,
            result: object,
            *,
            replay: bool = True,
        ) -> VariantPeptideDownstreamExportResult:
            del result, replay
            raise M1707ReplayVerificationError

    with TestClient(create_app(ReplayService())) as client:
        response = client.post("/v1/modules/M17-07/verify", json={"result": "ignored"})
        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
        assert response.json()["detail"] == "M17-07 replay verification failed"


def test_cli_schema_export_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(cli, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M17-07"

    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    exported = runner.invoke(cli, ["export", str(request_path), "--output", str(output_path)])
    assert exported.exit_code == 0
    verified = runner.invoke(cli, ["verify", str(output_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["status"] == "exported"

    refused = runner.invoke(cli, ["export", str(request_path), "--output", str(output_path)])
    assert refused.exit_code == CLI_REFUSED
    invalid = runner.invoke(cli, ["export", str(tmp_path / "missing.json")])
    assert invalid.exit_code == CLI_ERROR
    assert "Traceback" not in invalid.output

    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(build_scenario_request(accepted=False)))
    denied = runner.invoke(cli, ["export", str(denied_path)])
    assert denied.exit_code == CLI_REFUSED
    assert "authorization denied" in denied.output


def test_cli_reads_stdin_and_rejects_tampered_result(tmp_path: Path) -> None:
    runner = CliRunner()
    request = canonical_json_bytes(build_scenario_request()).decode()
    exported = runner.invoke(cli, ["export", "-"], input=request)
    assert exported.exit_code == 0
    body = json.loads(exported.stdout)
    body["result_digest"] = "sha256:" + "b" * 64
    result_path = tmp_path / "tampered.json"
    result_path.write_text(json.dumps(body), encoding="utf-8")
    verified = runner.invoke(cli, ["verify", str(result_path)])
    assert verified.exit_code == CLI_ERROR
    assert "Traceback" not in verified.output


def test_configuration_parent_target_cannot_drift() -> None:
    with pytest.raises(ValidationError, match="parent_target"):
        DownstreamExportConfiguration(
            configuration_id="configuration.bad",
            version="0.1.0",
            compatibility=CompatibilityMode.VERSIONED,
            parent_target="not-variant-peptide",  # type: ignore[arg-type]
        )


def test_field_type_catalogue_is_bounded_and_upstream_media_is_explicit() -> None:
    assert {member.value for member in ExportFieldType} == {
        "boolean",
        "decimal",
        "enum",
        "identifier",
        "reference",
        "text",
    }
    assert build_scenario_request().adjudication_result.media_type == M1707_M1706_INPUT_MEDIA_TYPE
