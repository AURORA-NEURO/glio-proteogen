"""Adversarial contract, replay, and adapter cases for M13-07."""

from __future__ import annotations

from collections import UserDict

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters import m1307
from glio_proteogen.contracts.m13_07 import (
    AdjudicateProteotypePlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityControl,
    PlausibilityGrade,
    canonical_request_digest,
    normalized_request,
    result_payload_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_07_plausibility_adjudicator as module,
)
from glio_proteogen.modules.c11_protein_native_subtype.m13_07_plausibility_adjudicator import (
    engine as module_impl,
)
from tests.modules.c11_protein_native_subtype.test_m13_07_engine import _request

_NOT_FOUND = 404
_BAD_REQUEST = 400
_UNPROCESSABLE = 422
_FORBIDDEN = 403
_CONFLICT = 409
_PAYLOAD_TOO_LARGE = 413


def test_contract_rejects_wrong_binding_duplicates_and_missing_control_kinds() -> None:
    request = _request()
    wrong_media = request.model_dump(mode="python")
    wrong_media["mechanism_inference_result"]["media_type"] = "application/json"
    with pytest.raises(ValueError, match="bind"):
        AdjudicateProteotypePlausibilityRequest.model_validate(wrong_media)

    duplicate_ids = request.model_dump(mode="python")
    duplicate_ids["controls"][1]["control_id"] = duplicate_ids["controls"][0]["control_id"]
    with pytest.raises(ValueError, match="unique"):
        AdjudicateProteotypePlausibilityRequest.model_validate(duplicate_ids)

    missing_kind = request.model_dump(mode="python")
    missing_kind["controls"][0]["kind"] = ControlKind.KNOWN_CONTROL
    with pytest.raises(ValueError, match="six required"):
        AdjudicateProteotypePlausibilityRequest.model_validate(missing_kind)


def test_contract_rejects_invalid_negative_control_and_no_negative_control() -> None:
    control = _request().controls[0].model_dump(mode="python")
    control["is_negative_control"] = True
    with pytest.raises(ValueError, match="known_control"):
        PlausibilityControl.model_validate(control)

    no_negative = _request().model_dump(mode="python")
    for item in no_negative["controls"]:
        item["is_negative_control"] = False
    with pytest.raises(ValueError, match="negative control"):
        AdjudicateProteotypePlausibilityRequest.model_validate(no_negative)


def test_contract_result_closure_rejects_outcome_and_direction_tampering() -> None:
    result = module.adjudicate_proteotype_plausibility(_request())
    tampered = result.model_copy(
        update={
            "evaluations": (
                result.evaluations[0].model_copy(update={"outcome": ControlOutcome.FAILED}),
                *result.evaluations[1:],
            )
        }
    )
    payload = tampered.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(tampered)
    with pytest.raises(ValueError, match="outcome"):
        type(result).model_validate(payload)


def test_contract_closure_rejects_duplicate_evaluations_conflicts_and_states() -> None:
    request = _request()
    with pytest.raises(ValueError, match="competing mechanisms"):
        request.model_copy(
            update={"candidate_mechanisms": ("only-one",), "conflict_declared": True}
        ).request_is_bound()

    result = module.adjudicate_proteotype_plausibility(request)
    duplicate_evaluations = result.model_copy(update={"evaluations": ()})
    with pytest.raises(ValueError, match="every control"):
        duplicate_evaluations.result_is_closed()

    failed = module.adjudicate_proteotype_plausibility(_request(outcome=ControlOutcome.FAILED))
    bad_abstention = failed.model_copy(update={"grade": PlausibilityGrade.LOW})
    with pytest.raises(ValueError, match="abstained"):
        bad_abstention.result_is_closed()

    bad_adjudication = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"status": SupportStatus.UNSUPPORTED}
            )
        }
    )
    with pytest.raises(ValueError, match="adjudicated"):
        bad_adjudication.result_is_closed()

    conflict = module.adjudicate_proteotype_plausibility(_request(conflict=True))
    duplicate_conflicts = conflict.model_copy(
        update={"conflicts": (*conflict.conflicts, *conflict.conflicts)}
    )
    with pytest.raises(ValueError, match="conflict ids"):
        duplicate_conflicts.result_is_closed()

    tampered = result.model_copy(
        update={
            "evaluations": (
                *result.evaluations[:2],
                result.evaluations[2].model_copy(update={"observed_direction": "opposite"}),
                *result.evaluations[3:],
            )
        }
    )
    payload = tampered.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(tampered)
    with pytest.raises(ValueError, match="direction"):
        type(result).model_validate(payload)


def test_canonical_dict_projection_and_hostile_mapping_fail_closed() -> None:
    assert normalized_request({"stable": True}) == {"stable": True}
    assert canonical_request_digest(_request()).startswith("sha256:")
    with pytest.raises(module.PlausibilityAuthorizationError):
        module.adjudicate_proteotype_plausibility(UserDict())
    with pytest.raises(module.PlausibilityAuthorizationError):
        module.preflight_plausibility_authorization(object())
    with pytest.raises(TypeError, match="string-keyed"):
        module_impl._plain_value(UserDict({"bad": 1}))


def test_preflight_hostile_member_exception_fails_closed(monkeypatch) -> None:
    def explode(*_args: object) -> object:
        raise RuntimeError

    monkeypatch.setattr(module_impl, "_member", explode)
    with pytest.raises(module.PlausibilityAuthorizationError):
        module.preflight_plausibility_authorization(_request())


def test_typed_request_plain_value_rejects_non_string_nested_keys() -> None:
    invalid = _request().model_dump(mode="python")
    invalid["source_artifacts"] = [{1: "bad"}]
    with pytest.raises(ValueError, match="contract"):
        module.adjudicate_proteotype_plausibility(invalid)


def test_replay_request_and_result_digest_failures() -> None:
    engine = module.M1307PlausibilityEngine()
    request = _request()
    result = engine.adjudicate(request)
    different_request = request.model_copy(update={"request_id": "different-request"})
    with pytest.raises(module.PlausibilityReplayError, match="request digest"):
        engine.verify(different_request, result)

    tampered = result.model_copy(update={"result_id": "tampered-result"})
    payload = tampered.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(tampered)
    valid_tamper = type(result).model_validate(payload)
    with pytest.raises(module.PlausibilityReplayError, match="deterministic replay"):
        engine.verify(request, valid_tamper)


def test_plugin_typed_path_descriptor_and_invalid_strict_json() -> None:
    plugin = module.M1307Plugin(module.M1307Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M13-07"
    assert plugin.validate(_request()).request.request_id == "request-m1307"
    with pytest.raises(module.PlausibilityAuthorizationError):
        plugin.validate('{"request_id":1}')
    invalid_json = (
        _request().model_dump_json().replace('"request_id":"request-m1307"', '"request_id":1')
    )
    with pytest.raises(ValueError, match="contract"):
        plugin.validate(invalid_json)


def test_adapter_error_branches_and_cli_rejections(tmp_path, monkeypatch) -> None:
    with pytest.raises(m1307._CliParameterError):
        m1307._read_json(tmp_path / "missing.json")
    oversized = tmp_path / "oversized.json"
    oversized.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(m1307, "M1307_MAX_CANONICAL_REQUEST_BYTES", 1)
    with pytest.raises(m1307._CliParameterError):
        m1307._read_json(oversized)
    with pytest.raises(m1307._CliParameterError):
        m1307._write_json(tmp_path / "missing" / "result.json", {})
    with pytest.raises(m1307.HTTPException):
        m1307.export_schema("unknown")

    request_path = tmp_path / "invalid.json"
    request_path.write_text("{}", encoding="utf-8")
    response = CliRunner().invoke(m1307.m1307_app, ["adjudicate", str(request_path)])
    assert response.exit_code != 0


def test_adapter_api_rejects_bad_schema_payloads_and_tamper() -> None:
    with TestClient(m1307.app) as client:
        assert client.get("/v1/modules/M13-07/schema/unknown").status_code == _NOT_FOUND
        assert (
            client.post("/v1/modules/M13-07/plausibility", content=b"not-json").status_code
            == _BAD_REQUEST
        )
        assert client.post("/v1/modules/M13-07/verify", json=[]).status_code == _UNPROCESSABLE
        assert (
            client.post("/v1/modules/M13-07/verify", json={"request": {}}).status_code == _FORBIDDEN
        )
    request = _request()
    result = module.adjudicate_proteotype_plausibility(request)
    tampered_model = result.model_copy(update={"result_id": "tampered-result"})
    tampered = tampered_model.model_dump(mode="json")
    tampered["result_digest"] = result_payload_digest(tampered_model)
    with TestClient(m1307.app) as client:
        response = client.post(
            "/v1/modules/M13-07/verify",
            json={"request": request.model_dump(mode="json"), "result": tampered},
        )
    assert response.status_code == _CONFLICT


def test_adapter_remaining_size_validation_and_cli_error_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(m1307, "M1307_MAX_CANONICAL_REQUEST_BYTES", 1)
    with TestClient(m1307.app) as client:
        assert (
            client.post("/v1/modules/M13-07/plausibility", content=b"{} ").status_code
            == _PAYLOAD_TOO_LARGE
        )
        assert (
            client.post("/v1/modules/M13-07/verify", content=b"{} ").status_code
            == _PAYLOAD_TOO_LARGE
        )
    monkeypatch.setattr(m1307, "M1307_MAX_CANONICAL_REQUEST_BYTES", 4 * 1024 * 1024)
    with TestClient(m1307.app) as client:
        assert (
            client.post("/v1/modules/M13-07/verify", json={"request": "wrong"}).status_code
            == _UNPROCESSABLE
        )
        assert (
            client.post(
                "/v1/modules/M13-07/verify",
                json={"request": _request().model_dump(mode="json"), "result": {}},
            ).status_code
            == _UNPROCESSABLE
        )
    runner = CliRunner()
    assert runner.invoke(m1307.m1307_app, ["export-schema", "output"]).exit_code == 0
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1307.m1307_app, ["adjudicate", str(invalid_path)]).exit_code != 0
    result_path = tmp_path / "result.json"
    result_path.write_text("{}", encoding="utf-8")
    assert (
        runner.invoke(m1307.m1307_app, ["verify", str(invalid_path), str(result_path)]).exit_code
        != 0
    )
    assert runner.invoke(m1307.m1307_app, ["export-schema", "unknown"]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(m1307.m1307_app, ["adjudicate", str(request_path)]).exit_code == 0


def test_api_validation_error_handler(monkeypatch) -> None:
    def fail(*_args: object) -> object:
        raise ValidationError.from_exception_data(
            "M13-07",
            [{"type": "missing", "loc": ("request",), "input": None}],
        )

    monkeypatch.setattr(m1307, "_validate_json_request", fail)
    with TestClient(m1307.app) as client:
        response = client.post(
            "/v1/modules/M13-07/plausibility",
            content=_request().model_dump_json(),
        )
    assert response.status_code == _UNPROCESSABLE
