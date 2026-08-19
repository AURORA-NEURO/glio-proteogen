"""Runtime and replay gates for M18-07 downstream typed export."""

# ruff: noqa: TRY003

from __future__ import annotations

import pytest
from pydantic import ValidationError

import glio_proteogen.modules.c18_spatial_proteomics_projection.m18_07_downstream_typed_export.engine as engine_module  # noqa: E501
from glio_proteogen.contracts.m18_07 import (
    BiomarkerPanelDownstreamExportResult,
    DownstreamContractObject,
    ExportStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_07_downstream_typed_export import (  # noqa: E501
    M1807AuthorizationError,
    M1807Engine,
    M1807ExportError,
    M1807Plugin,
    M1807ReplayError,
    M1807Service,
    ValidatedM1807Request,
)

from .test_m18_07_deep import _request


def test_supported_export_contains_signed_contract_and_all_uncertainty() -> None:
    result = M1807Engine().export(_request())
    assert result.status is ExportStatus.EXPORTED
    assert result.contract is not None
    assert (
        result.contract.signature.signed_payload_digest
        != result.contract.signature.signature_digest
    )
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M18-07"
    assert result.uncertainty.support.state.value == "estimated"


def test_abstention_preserves_unsupported_status_and_no_contract() -> None:
    request = _request().model_copy(
        update={
            "support_decision": _request().support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        }
    )
    result = M1807Engine().export(request)
    assert result.status is ExportStatus.ABSTAINED
    assert result.contract is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason
    assert result.human_review_required


def test_preflight_rejects_denied_control_before_validation() -> None:
    request = _request()
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "quality": request.context.references.quality.model_copy(
                                update={"state": "rejected"}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(M1807AuthorizationError, match="quality"):
        M1807Engine().export(denied)


def test_replay_and_tamper_detection() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    assert engine.verify(result).result_digest == result.result_digest
    tampered = result.model_dump(mode="json")
    tampered["result_digest"] = "sha256:" + "a" * 64
    with pytest.raises((M1807ReplayError, ValidationError)):
        engine.verify(tampered)


def test_verify_revalidates_model_copy_tampering_without_replay() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    tampered = result.model_copy(update={"contract": None})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises(M1807ReplayError):
        engine.verify(tampered, replay=False)


def test_replay_rejects_a_valid_but_different_request() -> None:
    engine = M1807Engine()
    original = engine.export(_request())
    assert original.contract is not None
    alternate_request = _request()
    alternate_field = alternate_request.fields[0].model_copy(
        update={"documentation": "Prohibited kinase boundary field."}
    )
    alternate_request = alternate_request.model_copy(update={"fields": (alternate_field,)})
    request_digest = canonical_request_digest(alternate_request)
    candidate = original.model_copy(
        update={
            "request": alternate_request,
            "request_digest": request_digest,
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "contract": original.contract.model_copy(update={"fields": (alternate_field,)}),
        }
    )
    candidate = candidate.model_copy(update={"result_digest": result_payload_digest(candidate)})
    with pytest.raises(M1807ReplayError, match="replay"):
        engine.verify(candidate)


def test_missing_controls_and_invalid_request_fail_closed() -> None:
    engine = M1807Engine()
    with pytest.raises(M1807AuthorizationError, match="seven"):
        engine.export({})
    with pytest.raises(M1807ExportError):
        engine.export({"context": _request().context.model_dump(mode="python")})


def test_contract_rejects_duplicate_names_and_inconsistent_ownership() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    assert result.contract is not None
    field = result.contract.fields[0]
    duplicate = field.model_copy(update={"field_name": field.field_id})
    with pytest.raises(ValidationError, match="id and name"):
        type(field).model_validate(duplicate.model_dump(mode="python"))
    contract = result.contract.model_dump(mode="python")
    contract["fields"] = (
        field.model_copy(update={"field_id": "field.other"}),
        field.model_copy(update={"field_id": "field.other", "field_name": "other_name"}),
    )
    with pytest.raises(ValidationError, match="field ids"):
        DownstreamContractObject.model_validate(contract)
    contract["fields"] = (
        field.model_copy(update={"field_id": "field.other"}),
        field.model_copy(update={"field_id": "field.third"}),
    )
    with pytest.raises(ValidationError, match="field names"):
        DownstreamContractObject.model_validate(contract)
    contract["fields"] = (field.model_copy(update={"owner": "Different owner"}),)
    with pytest.raises(ValidationError, match="ownership binding"):
        DownstreamContractObject.model_validate(contract)


def test_contract_rejects_parent_version_consent_support_and_module_tampering() -> None:
    result = M1807Engine().export(_request())
    assert result.contract is not None
    base = result.contract.model_dump(mode="python")
    cases = (
        (
            "consent",
            result.contract.consent.model_copy(update={"state": ConsentState.REVOKED}),
            "granted",
        ),
        (
            "support_decision",
            result.contract.support_decision.model_copy(update={"status": SupportStatus.LIMITED}),
            "supported",
        ),
        (
            "ownership",
            result.contract.ownership.model_copy(update={"owning_module": "GLIO-PROTEOGEN-M00-00"}),
            "M18-07",
        ),
        (
            "configuration",
            result.contract.configuration.model_copy(update={"parent_target": "biomarker panel"}),
            None,
        ),
    )
    for key, value, message in cases:
        candidate = dict(base)
        candidate[key] = value
        expected_message = message or "contract"
        if key == "configuration":
            candidate["parent_target"] = "biomarker panel"
            candidate["configuration"] = value.model_copy(update={"version": "2.0.0"})
            expected_message = "versions"
        with pytest.raises(ValidationError, match=expected_message):
            DownstreamContractObject.model_validate(candidate)

    candidate = dict(base)
    candidate["parent_target"] = "biomarker panel"
    candidate["configuration"] = result.contract.configuration.model_copy(
        update={"parent_target": "wrong-parent"}
    )
    with pytest.raises(ValidationError, match="parent"):
        DownstreamContractObject.model_validate(candidate)


def test_result_contract_rejects_digest_identity_and_state_tampering() -> None:
    engine = M1807Engine()
    result = engine.export(_request())
    raw = result.model_dump(mode="python")
    raw["request_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValidationError, match="request digest"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    raw = result.model_dump(mode="python")
    raw["result_id"] = "result.wrong"
    with pytest.raises(ValidationError, match="identifier"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    raw = result.model_dump(mode="python")
    raw["support_decision"] = result.support_decision.model_copy(
        update={"status": SupportStatus.UNSUPPORTED}
    )
    with pytest.raises(ValidationError, match="exported result"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    request = _request()
    field = request.fields[0].model_copy(
        update={"field_id": "field.other", "field_name": request.fields[0].field_name}
    )
    with pytest.raises(ValidationError, match="field names"):
        type(request).model_validate(
            request.model_copy(update={"fields": (request.fields[0], field)})
        )
    limited_support = request.support_decision.model_copy(update={"status": SupportStatus.LIMITED})
    abstained = engine.export(request.model_copy(update={"support_decision": limited_support}))
    raw = abstained.model_dump(mode="python")
    raw["contract"] = result.contract
    with pytest.raises(ValidationError, match="no contract"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    raw = abstained.model_dump(mode="python")
    raw["human_review_required"] = False
    with pytest.raises(ValidationError, match="human review"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    raw = result.model_dump(mode="python")
    raw["result_digest"] = "sha256:" + "c" * 64
    with pytest.raises(ValidationError, match="result digest"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)
    alternate = request.model_copy(
        update={"fields": (request.fields[0].model_copy(update={"field_id": "field.other"}),)}
    )
    raw = result.model_dump(mode="python")
    raw["request"] = alternate
    raw["request_digest"] = canonical_request_digest(alternate)
    raw["result_id"] = f"result.{raw['request_digest'].removeprefix('sha256:')}"
    with pytest.raises(ValidationError, match="bind request"):
        BiomarkerPanelDownstreamExportResult.model_validate(raw)


def test_service_direct_validate_and_execute_paths() -> None:
    service = M1807Service()
    request = _request()
    assert service.validate_request(request).request_id == request.request_id
    assert service.execute(request).status is ExportStatus.EXPORTED


def test_engine_error_paths_and_public_function(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    result = M1807Engine().export(request)
    assert M1807Engine().verify(result, replay=False) == result
    original_digest = engine_module.result_payload_digest
    monkeypatch.setattr(
        engine_module,
        "result_payload_digest",
        lambda _value: "sha256:" + "d" * 64,
    )
    with pytest.raises(M1807ReplayError, match="digest"):
        M1807Engine().verify(result)
    monkeypatch.setattr(engine_module, "result_payload_digest", original_digest)

    class FailingAdapter:
        def validate_python(self, _value: object, *, strict: bool) -> object:
            del strict
            raise ValueError("forced validation failure")

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", FailingAdapter())
    with pytest.raises(M1807ExportError, match="construction"):
        M1807Engine().export(request)
    monkeypatch.undo()
    assert (
        engine_module.export_biomarker_panel_downstream_contract(request).status
        is ExportStatus.EXPORTED
    )


def test_plugin_parse_once_seals_request_and_accepts_json() -> None:
    plugin = M1807Plugin(M1807Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M18-07"
    token = plugin.validate(_request())
    assert plugin.run(token).status is ExportStatus.EXPORTED
    json_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(json_token).status is ExportStatus.EXPORTED
    assert plugin.verify(plugin.run(token)).status is ExportStatus.EXPORTED
    forged = ValidatedM1807Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    with pytest.raises(StrictJsonError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
