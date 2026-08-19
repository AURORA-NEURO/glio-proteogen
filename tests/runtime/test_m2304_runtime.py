"""Runtime, replay, service, and plugin coverage for M23-04."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m23_04 import (
    EvaluationStatus,
    TransportStatus,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m23_04_external_transport_evaluator import (
    M2304AuthorizationError,
    M2304Engine,
    M2304Plugin,
    M2304ReplayError,
    M2304Service,
    M2304TokenError,
    evaluate_variant_peptide_external_transport,
)
from tests.contract.test_m2304_deep import _request

_CONTROL_COUNT = 7


def test_supported_request_emits_report_without_parent_estimate() -> None:
    result = evaluate_variant_peptide_external_transport(_request())
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.emits_parent is False
    assert result.parent_target == "variant peptide"
    assert result.support_decision.status.value == "supported"


def test_narrowed_dimension_remains_explicit_and_evaluable() -> None:
    request = _request()
    evaluations = tuple(
        item.model_copy(
            update={
                "status": TransportStatus.DOMAIN_NARROWED,
                "metric_value": 0.6,
            }
        )
        if item.dimension.value == "specimen"
        else item
        for item in request.evaluations
    )
    result = M2304Engine().evaluate(request.model_copy(update={"evaluations": evaluations}))
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.narrowed_dimensions
    assert result.report.support_domain.retained_dimensions


def test_not_evaluable_dimension_abstains_without_report() -> None:
    request = _request()
    evaluations = tuple(
        item.model_copy(update={"status": TransportStatus.NOT_EVALUABLE})
        if item.dimension.value == "platform"
        else item
        for item in request.evaluations
    )
    result = M2304Engine().evaluate(request.model_copy(update={"evaluations": evaluations}))
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason
    assert result.support_decision.status.value == "review_required"


def test_all_narrowed_dimensions_abstain_without_negative_output() -> None:
    request = _request()
    evaluations = tuple(
        item.model_copy(update={"status": TransportStatus.DOMAIN_NARROWED, "metric_value": 0.5})
        for item in request.evaluations
    )
    result = M2304Engine().evaluate(request.model_copy(update={"evaluations": evaluations}))
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.support_decision.status.value == "review_required"


def test_denied_control_fails_closed_before_evaluation() -> None:
    request = _request()
    references = request.context.references.model_copy(
        update={
            "quality": request.context.references.quality.model_copy(
                update={"state": UpstreamDecisionState.REJECTED}
            )
        }
    )
    context = request.context.model_copy(update={"references": references})
    with pytest.raises(M2304AuthorizationError):
        M2304Engine().evaluate(request.model_copy(update={"context": context}))


def test_hostile_mapping_fails_closed() -> None:
    with pytest.raises(M2304AuthorizationError):
        M2304Engine().evaluate({"context": {"references": None}})


def test_replay_accepts_exact_result_and_rejects_tamper() -> None:
    result = M2304Engine().evaluate(_request())
    assert M2304Engine().replay(result) == result
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})
    with pytest.raises(M2304ReplayError):
        M2304Engine().replay(tampered)


def test_service_accepts_canonical_json_and_replays() -> None:
    service = M2304Service()
    request = _request()
    result = service.evaluate(request.model_dump_json())
    assert service.verify_replay(result.model_dump_json()) == result
    mapped = service.evaluate(request.model_dump(mode="json"))
    assert service.verify_replay(mapped.model_dump(mode="json")) == mapped
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M23-04"


def test_plugin_token_is_parse_once_and_instance_bound() -> None:
    first = M2304Plugin()
    second = M2304Plugin()
    token = first.validate(_request())
    result = first.run(token)
    assert result.status is EvaluationStatus.EVALUATED
    with pytest.raises(M2304TokenError):
        second.run(token)


def test_plugin_rejects_nested_request_mutation_after_validation() -> None:
    plugin = M2304Plugin()
    token = plugin.validate(_request())
    changed_evaluation = token.request.evaluations[0].model_copy(
        update={"metric_value": token.request.evaluations[0].metric_value + 0.01}
    )
    object.__setattr__(
        token.request,
        "evaluations",
        (changed_evaluation, *token.request.evaluations[1:]),
    )
    with pytest.raises(M2304TokenError):
        plugin.run(token)


def test_plugin_rejects_forged_token() -> None:
    service = M2304Service()
    plugin = M2304Plugin(service)
    with pytest.raises(M2304TokenError):
        plugin.run(object())  # type: ignore[arg-type]
    plugin.validate_request(_request())
    result = service.evaluate(_request())
    assert plugin.replay(result) == result


def test_provenance_records_all_seven_controls() -> None:
    result = M2304Engine().evaluate(_request())
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert {item.role.value for item in result.provenance.control_decisions} == {
        "approved_configuration",
        "identity_lineage",
        "provenance",
        "consent",
        "quality",
        "support",
        "intended_use",
    }
