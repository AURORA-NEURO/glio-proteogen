"""Deep adversarial coverage for M24-05 subgroup equity boundaries."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest
from evals.m24_05.fixture import build_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m24_05 import (
    BiomarkerPanelSubgroupEvaluationResult,
    CoverageSummary,
    EquityStatus,
    EvaluationStatus,
    SubgroupFinding,
    SubgroupFindingCode,
    SubgroupPerformance,
    canonical_request_digest,
    result_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c21_reference_material import (
    m24_05_subgroup_equity_evaluator as m2405,
)
from tests.contract.test_m24_05_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = HTTPStatus.OK
_HTTP_UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY


def test_plugin_rejects_duplicate_keys_before_contract_parse() -> None:
    plugin = m2405.M2405Plugin(m2405.M2405Service())
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with pytest.raises(StrictJsonError) as error:
        plugin.validate(m2405.SubgroupEvaluationSubmission(duplicate))
    assert error.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_plugin_rejects_unwrapped_and_unvalidated_execution() -> None:
    plugin = m2405.M2405Plugin(m2405.M2405Service())
    request = _request()
    with pytest.raises(TypeError, match="subgroup-evaluation submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_hostile_mapping_fails_closed_before_material_traversal() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2405.M2405AuthorizationError):
        m2405.preflight_m2405_authorization(ExplodingMapping())
    with pytest.raises(m2405.M2405AuthorizationError):
        m2405.M2405Service().validate_request(ExplodingMapping())


def test_service_rejects_unknown_fields_wrong_media_and_missing_dimension() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2405.M2405Service().validate_request(payload)
    with pytest.raises(ValidationError, match="M24-04"):
        m2405.M2405Service().validate_request(
            request.model_copy(
                update={
                    "upstream_result": request.upstream_result.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            )
        )
    with pytest.raises(ValidationError, match="coverage must cover"):
        m2405.M2405Service().validate_request(
            request.model_copy(update={"coverage": request.coverage[:-1]})
        )


def test_contract_rejects_invalid_performance_and_coverage_math() -> None:
    request = _request()
    performance = request.performance[0]
    invalid_performance = performance.model_dump(mode="python") | {
        "lower_bound": 0.99,
        "upper_bound": 0.9,
    }
    with pytest.raises(ValidationError, match="bounds are not ordered"):
        SubgroupPerformance.model_validate(invalid_performance, strict=True)
    invalid_value = performance.model_dump(mode="python") | {"value": 0.5}
    with pytest.raises(ValidationError, match="within bounds"):
        SubgroupPerformance.model_validate(invalid_value, strict=True)
    invalid_floor = performance.model_dump(mode="python") | {
        "equity_status": EquityStatus.BELOW_FLOOR,
    }
    with pytest.raises(ValidationError, match="below-floor"):
        SubgroupPerformance.model_validate(invalid_floor, strict=True)
    coverage = request.coverage[0]
    with pytest.raises(ValidationError, match="cannot exceed"):
        CoverageSummary.model_validate(
            coverage.model_dump(mode="python")
            | {"supported_examples": 101, "coverage_fraction": 1.0},
            strict=True,
        )
    with pytest.raises(ValidationError, match="coverage fraction"):
        CoverageSummary.model_validate(
            coverage.model_dump(mode="python") | {"coverage_fraction": 0.1},
            strict=True,
        )


def test_contract_rejects_duplicate_result_findings_and_identity_forgery() -> None:
    service = m2405.M2405Service()
    result = service.evaluate(_request())
    assert result.request_digest == canonical_request_digest(result.request)
    assert result.result_id == result_identifier(result.request)
    finding = SubgroupFinding(
        finding_id="m2405.duplicate",
        code=SubgroupFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
        message="review required",
    )
    updates: tuple[dict[str, object], ...] = (
        {"result_id": "result.forged"},
        {"request_digest": "sha256:" + "0" * 64},
        {"provenance": result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M24-06"})},
        {
            "provenance": result.provenance.model_copy(
                update={"input_digests": ("sha256:" + "0" * 64,)}
            )
        },
        {"findings": (finding, finding)},
    )
    for update in updates:
        with pytest.raises(ValidationError):
            BiomarkerPanelSubgroupEvaluationResult.model_validate(
                result.model_dump(mode="python") | update,
                strict=True,
            )


def test_api_rejects_nonobject_duplicate_and_tampered_verify_payloads() -> None:
    request = _request()
    client = TestClient(m2405.create_app(m2405.M2405Service()))
    assert client.post("/v1/modules/M24-05/verify", json=[]).status_code == _HTTP_UNPROCESSABLE
    evaluated = client.post(
        "/v1/modules/M24-05/evaluate",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    )
    assert evaluated.status_code == _HTTP_OK
    forged = evaluated.json()
    forged["result_digest"] = "sha256:" + "f" * 64
    response = client.post("/v1/modules/M24-05/verify", json=forged)
    assert response.status_code == _HTTP_UNPROCESSABLE
    duplicate = client.post(
        "/v1/modules/M24-05/validate",
        content=b'{"request_id":"safe","request_id":"sensitive-second"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive-second" not in duplicate.text


def test_api_denial_is_sanitized() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    response = TestClient(m2405.create_app(m2405.M2405Service())).post(
        "/v1/modules/M24-05/evaluate", json=denied.model_dump(mode="json")
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_bad_input_and_no_overwrite_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m2405.cli.app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(m2405.cli.app, ["validate", str(bad_request)]).exit_code != 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            m2405.cli.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    original = result_path.read_bytes()
    assert (
        runner.invoke(
            m2405.cli.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert result_path.read_bytes() == original


def test_abstained_result_is_explicit_and_safe() -> None:
    request = build_request()
    performance = request.performance[0].model_copy(
        update={
            "value": 0.7,
            "lower_bound": 0.6,
            "upper_bound": 0.8,
            "equity_status": EquityStatus.BELOW_FLOOR,
        }
    )
    result = m2405.M2405Service().evaluate(
        request.model_copy(update={"performance": (performance, *request.performance[1:])})
    )
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.emits_parent is False
