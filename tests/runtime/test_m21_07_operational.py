"""Runtime, service, plugin, replay, and abstention coverage for M21-07."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m21_07 import (
    EvaluationStatus,
    OperationalDimension,
    OperationalFindingCode,
    OperationalStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_reference_material.m21_07_human_factors_operational_evaluator import (  # noqa: E501
    M2107AuthorizationError,
    M2107Engine,
    M2107Plugin,
    M2107ReplayError,
    M2107Service,
    ValidatedM2107Request,
    evaluate_complex_activity_human_factors,
    preflight_m2107_authorization,
)
from tests.contract.test_m21_07_hardening import _metric, _request


def _metrics(status: OperationalStatus) -> tuple:
    return tuple(_metric(dimension, status) for dimension in OperationalDimension)


def test_engine_evaluates_seven_dimensions_and_replays_exactly() -> None:
    request = _request()
    result = M2107Engine().evaluate(request)

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert {item.dimension for item in result.report.metrics} == set(OperationalDimension)
    assert result.human_review_required is True
    assert M2107Engine().replay(result) == result


def test_failed_operational_dimensions_are_visible_findings() -> None:
    statuses = list((OperationalStatus.PASS,) * len(tuple(OperationalDimension)))
    statuses[1] = OperationalStatus.FAIL
    result = M2107Engine().evaluate(_request(statuses=tuple(statuses)))

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert any(item.code is OperationalFindingCode.AUTOMATION_BIAS_RISK for item in result.findings)


def test_non_evaluable_operational_material_abstains_without_report() -> None:
    statuses = list((OperationalStatus.PASS,) * len(tuple(OperationalDimension)))
    statuses[0] = OperationalStatus.NOT_EVALUABLE
    result = M2107Engine().evaluate(_request(statuses=tuple(statuses)))

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_authorization_is_fail_closed_before_evaluation() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    references = request.context.references.model_copy(update={"consent": consent})
    context = request.context.model_copy(update={"references": references})

    with pytest.raises(M2107AuthorizationError):
        M2107Engine().evaluate(request.model_copy(update={"context": context}))


def test_service_and_plugin_keep_parse_once_and_token_boundaries() -> None:
    request = _request()
    service = M2107Service()
    result = service.evaluate(request.model_dump_json())
    assert service.replay(result.model_dump_json()) == result
    mapped = service.evaluate(request.model_dump(mode="json"))
    assert service.replay(mapped.model_dump(mode="json")) == mapped

    plugin = M2107Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token) == result
    assert plugin.replay(result) == result
    plugin.validate_request(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(ValidatedM2107Request(request, object()))
    sealed = plugin.validate(request)
    sealed._seal = object()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(sealed)
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M21-07"


def test_plugin_rejects_cross_instance_and_nested_request_mutation() -> None:
    request = _request()
    service = M2107Service()
    plugin = M2107Plugin(service)
    other = M2107Plugin(service)
    token = plugin.validate(request)

    with pytest.raises(TypeError, match="validated request token"):
        other.run(token)

    changed_metric = token.request.metrics[0].model_copy(update={"observed_value": 0.1})
    object.__setattr__(
        token.request,
        "metrics",
        (changed_metric, *token.request.metrics[1:]),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_replay_rejects_tampering_and_public_entry_point_is_deterministic() -> None:
    request = _request()
    result = evaluate_complex_activity_human_factors(request)
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(M2107ReplayError):
        M2107Engine().replay(tampered)
    with pytest.raises(M2107ReplayError):
        M2107Engine().replay(result.model_copy(update={"result_id": "result.forged"}))
    with pytest.raises(M2107ReplayError):
        M2107Engine().replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    assert evaluate_complex_activity_human_factors(request) == result


def test_preflight_accepts_mapping_context_shape() -> None:
    request = _request()
    preflight_m2107_authorization({"context": request.context})
