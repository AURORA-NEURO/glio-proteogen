"""Deterministic runtime and safe-abstention tests for M24-05."""

from __future__ import annotations

import json

import pytest

from glio_proteogen.contracts.m24_05 import (
    CoverageStatus,
    EquityStatus,
    EvaluationStatus,
    SubgroupDimension,
)
from glio_proteogen.kernel.models import (
    EstimateState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_05_subgroup_equity_evaluator as m2405,
)
from tests.contract.test_m24_05_hardening import _request

_CONTROL_COUNT = 7


def test_supported_evaluation_closes_report_provenance_and_uncertainty() -> None:
    service = m2405.M2405Service()
    result = service.evaluate(_request())
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.findings == ()
    assert result.emits_parent is False
    assert result.parent_target == "biomarker panel"
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.request.upstream_result.digest in result.provenance.input_digests
    assert all(
        estimate.state is EstimateState.NOT_ESTIMABLE
        for estimate in (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
    )


def test_repeat_json_and_replay_are_byte_deterministic() -> None:
    service = m2405.M2405Service()
    request = _request()
    first = service.evaluate(request)
    second = service.evaluate(json.dumps(request.model_dump(mode="json"), sort_keys=True))
    assert first.result_digest == second.result_digest
    assert service.export_json(first) == service.export_json(second)
    assert service.verify_replay(first).result_digest == first.result_digest


def test_safety_floor_breach_abstains_without_report() -> None:
    request = _request()
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
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert any(finding.code.value == "safety_floor_breach" for finding in result.findings)


def test_unsupported_coverage_and_calibration_abstain() -> None:
    request = _request()
    unsupported = request.coverage[0].model_copy(update={"status": CoverageStatus.NOT_EVALUABLE})
    unsupported_result = m2405.M2405Service().evaluate(
        request.model_copy(update={"coverage": (unsupported, *request.coverage[1:])})
    )
    assert unsupported_result.status is EvaluationStatus.ABSTAINED
    assert unsupported_result.report is None

    calibration = request.calibration[0].model_copy(update={"status": EvaluationStatus.ABSTAINED})
    calibration_result = m2405.M2405Service().evaluate(
        request.model_copy(update={"calibration": (calibration, *request.calibration[1:])})
    )
    assert calibration_result.status is EvaluationStatus.ABSTAINED
    assert any(
        finding.code.value == "calibration_failure" for finding in calibration_result.findings
    )


def test_rare_context_limited_coverage_abstains() -> None:
    request = _request()
    rare_index = next(
        index
        for index, item in enumerate(request.coverage)
        if item.dimension is SubgroupDimension.RARE_BIOLOGICAL_STATE
    )
    rare = request.coverage[rare_index].model_copy(update={"status": CoverageStatus.LIMITED})
    coverage = (*request.coverage[:rare_index], rare, *request.coverage[rare_index + 1 :])
    result = m2405.M2405Service().evaluate(request.model_copy(update={"coverage": coverage}))
    assert result.status is EvaluationStatus.ABSTAINED
    assert any(finding.code.value == "rare_context_unsupported" for finding in result.findings)


def test_replay_rejects_request_identity_and_payload_tamper() -> None:
    service = m2405.M2405Service()
    result = service.evaluate(_request())
    changed_request = result.request.model_copy(update={"request_id": "changed"})
    with pytest.raises(m2405.M2405ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request": changed_request}))
    with pytest.raises(m2405.M2405ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "result.forged"}))
    with pytest.raises(m2405.M2405ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))


def test_denied_control_and_hostile_mapping_fail_closed() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(m2405.M2405AuthorizationError):
        m2405.M2405Service().evaluate(denied)

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2405.M2405AuthorizationError):
        m2405.M2405Service().validate_request(ExplodingMapping())
