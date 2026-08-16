"""Deep adversarial coverage for M24-07 safety, replay and interface boundaries."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest
from evals.m24_07.fixture import request as fixture_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m24_07 import (
    BiomarkerPanelHumanFactorsResult,
    EvaluationStatus,
    OperationalConfiguration,
    OperationalDimension,
    OperationalFinding,
    OperationalFindingCode,
    OperationalMetric,
    OperationalStatus,
    canonical_request_digest,
    result_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material import (
    m24_07_human_factors_operational_evaluator as m2407,
)
from tests.contract.test_m24_07_hardening import request as request_payload

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = HTTPStatus.OK
_HTTP_UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY
_SCHEMA_COUNT = 7


def test_plugin_rejects_duplicate_keys_before_contract_parse() -> None:
    plugin = m2407.M2407Plugin(m2407.M2407Service())
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(m2407.HumanFactorsSubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_and_unvalidated_execution() -> None:
    plugin = m2407.M2407Plugin(m2407.M2407Service())
    typed = fixture_request()
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(typed)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", typed))
    token = plugin.validate(m2407.HumanFactorsSubmission(typed))
    assert plugin.run(token).status is EvaluationStatus.EVALUATED


def test_hostile_mapping_fails_closed_before_material_traversal() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2407.M2407AuthorizationError):
        m2407.preflight_m2407_authorization(ExplodingMapping())
    with pytest.raises(m2407.M2407AuthorizationError):
        m2407.M2407Service().validate_request(ExplodingMapping())


def test_service_rejects_unknown_fields_wrong_media_and_incomplete_dimensions() -> None:
    typed = fixture_request()
    payload = typed.model_dump(mode="python")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2407.M2407Service().validate_request(payload)
    with pytest.raises(ValidationError, match="M24-06"):
        m2407.M2407Service().validate_request(
            typed.model_copy(
                update={
                    "upstream_result": typed.upstream_result.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="every configured"):
        m2407.M2407Service().validate_request(
            typed.model_copy(update={"metrics": typed.metrics[:-1]})
        )


def test_contract_rejects_invalid_metric_math_and_configuration_closure() -> None:
    typed = fixture_request()
    metric = typed.metrics[0]
    with pytest.raises(ValidationError, match="within its declared tolerance"):
        OperationalMetric.model_validate(
            metric.model_dump(mode="python")
            | {"observed_value": 2.0, "target_value": 1.0, "tolerance": 0.1},
            strict=True,
        )
    with pytest.raises(ValidationError, match="not-evaluable"):
        OperationalMetric.model_validate(
            metric.model_dump(mode="python")
            | {"sample_size": 3, "status": OperationalStatus.NOT_EVALUABLE},
            strict=True,
        )
    configuration = typed.configuration
    with pytest.raises(ValidationError, match="all operational dimensions"):
        OperationalConfiguration.model_validate(
            configuration.model_dump(mode="python")
            | {"required_dimensions": (OperationalDimension.LATENCY,) * _SCHEMA_COUNT},
            strict=True,
        )


def test_result_closure_rejects_identity_provenance_and_duplicate_finding_forgery() -> None:
    service = m2407.M2407Service()
    result = service.evaluate(fixture_request())
    assert result.request_digest == canonical_request_digest(result.request)
    assert result.result_id == result_identifier(result.request)
    finding = OperationalFinding(
        finding_id="m2407.duplicate",
        code=OperationalFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        message="review required",
        evidence=result.evidence,
    )
    updates: tuple[dict[str, object], ...] = (
        {"result_id": "result.forged"},
        {"request_digest": "sha256:" + "0" * 64},
        {"provenance": result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M24-06"})},
        {"findings": (finding, finding)},
    )
    for update in updates:
        with pytest.raises(ValidationError):
            BiomarkerPanelHumanFactorsResult.model_validate(
                result.model_dump(mode="python") | update,
                strict=True,
            )
    with pytest.raises(ValidationError, match="abstained result"):
        BiomarkerPanelHumanFactorsResult.model_validate(
            result.model_dump(mode="python")
            | {
                "status": EvaluationStatus.ABSTAINED,
                "abstention_reason": "review required",
                "support_decision": result.support_decision.model_copy(
                    update={"status": SupportStatus.REVIEW_REQUIRED}
                ),
            },
            strict=True,
        )


def test_api_rejects_nonobject_duplicate_and_tampered_verify_payloads() -> None:
    typed = fixture_request()
    client = TestClient(m2407.create_app(m2407.M2407Service()))
    assert client.post("/v1/modules/M24-07/verify", json=[]).status_code == _HTTP_UNPROCESSABLE
    evaluated = client.post(
        "/v1/modules/M24-07/evaluate",
        content=canonical_json_bytes(typed),
        headers={"content-type": "application/json"},
    )
    assert evaluated.status_code == _HTTP_OK
    forged = evaluated.json()
    forged["result_digest"] = "sha256:" + "f" * 64
    response = client.post("/v1/modules/M24-07/verify", json=forged)
    assert response.status_code == _HTTP_UNPROCESSABLE
    duplicate = client.post(
        "/v1/modules/M24-07/validate",
        content=b'{"request_id":"safe","request_id":"sensitive-second"}',
    )
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive-second" not in duplicate.text


def test_api_denial_is_sanitized() -> None:
    typed = fixture_request()
    support = typed.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_context = typed.context.model_copy(
        update={"references": typed.context.references.model_copy(update={"support": support})}
    )
    denied = typed.model_copy(update={"context": denied_context})
    response = TestClient(m2407.create_app(m2407.M2407Service())).post(
        "/v1/modules/M24-07/evaluate", json=denied.model_dump(mode="json")
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_bad_input_and_no_overwrite_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m2407.cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(m2407.cli_app, ["validate", str(bad_request)]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(fixture_request()))
    result_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            m2407.cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    original = result_path.read_bytes()
    assert (
        runner.invoke(
            m2407.cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert result_path.read_bytes() == original


def test_public_entry_point_and_strict_json_size_limit_are_deterministic() -> None:
    typed = fixture_request()
    first = m2407.evaluate_biomarker_panel_human_factors_operational(typed)
    second = m2407.evaluate_biomarker_panel_human_factors_operational(canonical_json_bytes(typed))
    assert first.result_digest == second.result_digest
    with pytest.raises(StrictJsonError, match="exceeds the byte limit"):
        m2407.M2407Plugin(m2407.M2407Service()).validate(
            m2407.HumanFactorsSubmission(b"{" + b"x" * (4 * 1024 * 1024) + b"}")
        )


def test_media_boundary_is_caller_declared_and_never_imports_m24_06() -> None:
    source = request_payload()
    upstream = cast("dict[str, object]", source["upstream_result"])
    assert str(upstream["media_type"]).endswith("m24-06+json")
    assert "m24_06" not in m2407.__name__
