"""Runtime, service and strict-plugin tests for M21-05."""

from __future__ import annotations

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m21_05 import CoverageStatus, EquityStatus, EvaluationStatus
from glio_proteogen.kernel.models import ConsentState, SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    M2105AuthorizationError,
    M2105Engine,
    M2105EvaluationError,
    M2105Plugin,
    M2105ReplayError,
    M2105Service,
    M2105TokenError,
    ValidatedM2105Request,
)
from tests.contract.test_m21_05_adversarial import (
    _request,
    _result,
)


def test_nominal_evaluation_is_deterministic_and_replayable() -> None:
    engine = M2105Engine()
    first = engine.evaluate(_request())
    second = engine.evaluate(_request())

    assert first == second
    assert first.status is EvaluationStatus.EVALUATED
    assert first.report is not None
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.emits_parent is False
    assert first.human_review_required is False
    assert engine.verify(first).result_digest == first.result_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coverage_status", CoverageStatus.UNSUPPORTED),
        ("coverage_status", CoverageStatus.NOT_EVALUABLE),
        ("coverage_status", CoverageStatus.LIMITED),
        ("equity_status", EquityStatus.BELOW_FLOOR),
    ],
)
def test_unsafe_subgroup_evidence_abstains_without_report(
    field: str,
    value: object,
) -> None:
    request = _request()
    performance = list(request.performance)
    updates: dict[str, object] = {field: value}
    if field == "equity_status":
        updates.update({"value": 0.4, "lower_bound": 0.3, "upper_bound": 0.5})
    performance[0] = performance[0].model_copy(update=updates)
    request = request.model_copy(update={"performance": tuple(performance)})

    result = M2105Engine().evaluate(request)

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.human_review_required is True
    assert result.support_decision.status in {
        SupportStatus.UNSUPPORTED,
        SupportStatus.REVIEW_REQUIRED,
    }


def test_coverage_and_calibration_failures_are_safe_abstentions() -> None:
    request = _request()
    coverage = list(request.coverage)
    coverage[0] = coverage[0].model_copy(update={"status": CoverageStatus.NOT_EVALUABLE})
    calibration = list(request.calibration)
    calibration[0] = calibration[0].model_copy(
        update={"nominal_coverage": 0.5, "status": EvaluationStatus.EVALUATED}
    )
    request = request.model_copy(
        update={"coverage": tuple(coverage), "calibration": tuple(calibration)}
    )

    result = M2105Engine().evaluate(request)

    assert result.status is EvaluationStatus.ABSTAINED
    assert {finding.code.value for finding in result.findings} >= {
        "coverage_limited",
        "calibration_failure",
    }


@pytest.mark.parametrize(
    "field",
    ["approved_configuration", "provenance", "quality", "support", "intended_use"],
)
def test_denied_upstream_control_fails_before_evaluation(field: str) -> None:
    request = _request()
    decision = request.context.references.__getattribute__(field)
    denied = decision.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    references = request.context.references.model_copy(update={field: denied})
    request = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )

    with pytest.raises(M2105AuthorizationError):
        M2105Engine().evaluate(request)


def test_revoked_consent_and_unresolved_identity_fail_closed() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.REVOKED})
    references = request.context.references.model_copy(update={"consent": consent})
    revoked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2105AuthorizationError):
        M2105Engine().evaluate(revoked)

    identity = request.context.references.identity_lineage.model_copy(
        update={"state": "unresolved"}
    )
    references = request.context.references.model_copy(update={"identity_lineage": identity})
    unresolved = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2105AuthorizationError):
        M2105Engine().evaluate(unresolved)


def test_service_validates_and_plugin_parse_once_requires_sealed_token() -> None:
    request = _request()
    service = M2105Service()
    validated = service.validate_request(request)
    result = service.execute(validated)
    assert result.status is EvaluationStatus.EVALUATED
    assert service.verify(result).result_id == result.result_id

    plugin = M2105Plugin(service)
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-05"
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())


def test_plugin_token_rejects_forged_cross_instance_and_nested_mutation() -> None:
    request = _request()
    plugin = M2105Plugin()
    other = M2105Plugin()
    token = plugin.validate(request)

    assert plugin.run(token).status is EvaluationStatus.EVALUATED

    forged = ValidatedM2105Request(request=token.request, _seal=token._seal)
    with pytest.raises(M2105TokenError):
        plugin.run(forged)
    with pytest.raises(M2105TokenError):
        other.run(token)

    changed_performance = token.request.performance[0].model_copy(update={"value": 0.1})
    object.__setattr__(
        token.request,
        "performance",
        (changed_performance, *token.request.performance[1:]),
    )
    with pytest.raises(M2105TokenError):
        plugin.run(token)


def test_replay_rejects_payload_and_request_tampering() -> None:
    engine = M2105Engine()
    result = engine.evaluate(_request())
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    with pytest.raises(M2105ReplayError):
        engine.verify(tampered, replay=False)

    changed_request = _request().model_copy(update={"request_id": "request.m2105.changed"})
    request_tampered = result.model_copy(update={"request": changed_request})
    with pytest.raises(M2105ReplayError):
        engine.verify(request_tampered, replay=False)


def test_invalid_request_is_sanitized() -> None:
    with pytest.raises((M2105AuthorizationError, M2105EvaluationError)):
        M2105Engine().evaluate({"request_id": "bad"})


def test_result_fixture_is_valid_for_replay_contract() -> None:
    result = _result()
    assert result.status is EvaluationStatus.EVALUATED
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.report is not None
