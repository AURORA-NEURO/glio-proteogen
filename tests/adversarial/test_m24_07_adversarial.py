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
    HumanFactorsOperationalReport,
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
    with pytest.raises(ValidationError, match="cover downtime"):
        m2407.M2407Service().validate_request(
            typed.model_copy(update={"fallbacks": (typed.fallbacks[0],)})
        )
    duplicate_metrics = typed.model_copy(update={"metrics": (typed.metrics[0], *typed.metrics)})
    with pytest.raises(ValidationError, match="metric ids must be unique"):
        m2407.M2407Service().validate_request(duplicate_metrics)
    duplicate_fallbacks = typed.model_copy(
        update={"fallbacks": (typed.fallbacks[0], *typed.fallbacks)}
    )
    with pytest.raises(ValidationError, match="fallback ids must be unique"):
        m2407.M2407Service().validate_request(duplicate_fallbacks)


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
    with pytest.raises(ValidationError, match="operational metric ids"):
        HumanFactorsOperationalReport.model_validate(
            {
                "report_id": "m2407.report.duplicate",
                "version": "1.0.0",
                "metrics": (typed.metrics[0], *typed.metrics),
                "fallbacks": typed.fallbacks,
                "configuration": typed.configuration,
                "evidence": typed.configuration.evidence,
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="fallback scenario ids"):
        HumanFactorsOperationalReport.model_validate(
            {
                "report_id": "m2407.report.duplicate-fallback",
                "version": "1.0.0",
                "metrics": typed.metrics,
                "fallbacks": (typed.fallbacks[0], *typed.fallbacks),
                "configuration": typed.configuration,
                "evidence": typed.configuration.evidence,
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="measure every"):
        HumanFactorsOperationalReport.model_validate(
            {
                "report_id": "m2407.report.missing-metric",
                "version": "1.0.0",
                "metrics": typed.metrics[:-1],
                "fallbacks": typed.fallbacks,
                "configuration": typed.configuration,
                "evidence": typed.configuration.evidence,
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="cover downtime"):
        HumanFactorsOperationalReport.model_validate(
            {
                "report_id": "m2407.report.missing-fallback",
                "version": "1.0.0",
                "metrics": typed.metrics,
                "fallbacks": (typed.fallbacks[0],),
                "configuration": typed.configuration,
                "evidence": typed.configuration.evidence,
            },
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
        {"report": None},
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
    assert client.get("/v1/modules/M24-07/schemas/request").status_code == _HTTP_OK
    invalid_json = client.post("/v1/modules/M24-07/verify", content=b"{")
    assert invalid_json.status_code == _HTTP_UNPROCESSABLE


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
    validate_response = TestClient(m2407.create_app(m2407.M2407Service())).post(
        "/v1/modules/M24-07/validate", json=denied.model_dump(mode="json")
    )
    assert validate_response.status_code == _HTTP_UNPROCESSABLE


def test_cli_bad_input_and_no_overwrite_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    schema_path = tmp_path / "schema.json"
    assert (
        runner.invoke(
            m2407.cli_app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(m2407.cli_app, ["evaluate", str(request_path)]).exit_code == 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"{}")
    assert runner.invoke(m2407.cli_app, ["verify", str(bad_result)]).exit_code != 0
    denied = fixture_request()
    support = denied.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_references = denied.context.references.model_copy(update={"support": support})
    denied = denied.model_copy(
        update={"context": denied.context.model_copy(update={"references": denied_references})}
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(denied))
    assert runner.invoke(m2407.cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(m2407.cli_app, ["evaluate", str(denied_path)]).exit_code != 0
    baseline = fixture_request()
    failed_metric = baseline.metrics[0].model_copy(update={"status": OperationalStatus.FAIL})
    failed = baseline.model_copy(update={"metrics": (failed_metric, *baseline.metrics[1:])})
    failed_path = tmp_path / "failed.json"
    failed_path.write_bytes(canonical_json_bytes(failed))
    assert runner.invoke(m2407.cli_app, ["evaluate", str(failed_path)]).exit_code == 1

    class ReplayFailure:
        def verify_replay(self, _result: object) -> object:
            raise ValueError("replay failure")  # noqa: TRY003

    monkeypatch.setattr(m2407.cli, "_SERVICE", ReplayFailure())
    assert runner.invoke(m2407.cli_app, ["verify", str(result_path)]).exit_code != 0

    class ReplayMismatch:
        def verify_replay(self, _result: object) -> object:
            result = m2407.M2407Service().evaluate(fixture_request())
            return result.model_copy(update={"result_digest": "sha256:" + "f" * 64})

    monkeypatch.setattr(m2407.cli, "_SERVICE", ReplayMismatch())
    assert runner.invoke(m2407.cli_app, ["verify", str(result_path)]).exit_code == 1


def test_public_entry_point_and_strict_json_size_limit_are_deterministic() -> None:
    typed = fixture_request()
    first = m2407.evaluate_biomarker_panel_human_factors_operational(typed)
    second = m2407.evaluate_biomarker_panel_human_factors_operational(canonical_json_bytes(typed))
    assert first.result_digest == second.result_digest
    with pytest.raises(StrictJsonError, match="exceeds the byte limit"):
        m2407.M2407Plugin(m2407.M2407Service()).validate(
            m2407.HumanFactorsSubmission(b"{" + b"x" * (4 * 1024 * 1024) + b"}")
        )
    assert m2407.M2407Plugin(m2407.M2407Service()).descriptor().module_id == "GLIO-PROTEOGEN-M24-07"


def test_media_boundary_is_caller_declared_and_never_imports_m24_06() -> None:
    source = request_payload()
    upstream = cast("dict[str, object]", source["upstream_result"])
    assert str(upstream["media_type"]).endswith("m24-06+json")
    assert "m24_06" not in m2407.__name__
