"""Runtime, service, plugin, replay, and abstention coverage for M21-04."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m21_04 import (
    EvaluationStatus,
    TransportDimension,
    TransportFindingCode,
    TransportStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_reference_material.m21_04_external_transport_evaluator import (
    M2104AuthorizationError,
    M2104Engine,
    M2104Plugin,
    M2104ReplayError,
    M2104Service,
    ValidatedM2104Request,
    evaluate_complex_activity_external_transport,
)
from tests.contract.test_m21_04_hardening import _evaluation, _request

UNCERTAINTY_DIMENSION_COUNT = 8


def _evaluations(status: TransportStatus) -> tuple:
    return tuple(_evaluation(dimension, status) for dimension in TransportDimension)


def test_engine_evaluates_all_dimensions_and_replays_exactly() -> None:
    request = _request()
    result = M2104Engine().evaluate(request)

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.retained_dimensions == tuple(TransportDimension)
    assert len(result.uncertainty.model_dump()) == UNCERTAINTY_DIMENSION_COUNT
    assert M2104Engine().replay(result) == result


def test_domain_narrowing_preserves_explicit_support_boundary() -> None:
    evaluations = list(_evaluations(TransportStatus.SUPPORTED))
    evaluations[0] = _evaluation(TransportDimension.SITE, TransportStatus.DOMAIN_NARROWED)
    result = M2104Engine().evaluate(_request(evaluations=tuple(evaluations)))

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    support = result.report.support_domain
    assert support.status is TransportStatus.DOMAIN_NARROWED
    assert support.narrowed_dimensions == (TransportDimension.SITE,)
    assert TransportDimension.SITE not in support.retained_dimensions
    assert any(
        item.code is TransportFindingCode.SUPPORT_DOMAIN_NARROWED for item in result.findings
    )


@pytest.mark.parametrize(
    ("status", "expected_reason"),
    [
        (TransportStatus.NOT_EVALUABLE, "not safely evaluable"),
        (TransportStatus.DOMAIN_NARROWED, "No retained external transport"),
    ],
)
def test_unsafe_transport_support_abstains_without_report(
    status: TransportStatus, expected_reason: str
) -> None:
    result = M2104Engine().evaluate(_request(evaluations=_evaluations(status)))

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert expected_reason.lower() in result.abstention_reason.lower()
    assert result.support_decision.status.value == "review_required"


def test_authorization_is_fail_closed_before_evaluation() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    references = request.context.references.model_copy(update={"consent": consent})
    context = request.context.model_copy(update={"references": references})

    with pytest.raises(M2104AuthorizationError):
        M2104Engine().evaluate(request.model_copy(update={"context": context}))


def test_service_and_plugin_keep_parse_once_and_token_boundaries() -> None:
    request = _request()
    service = M2104Service()
    result = service.evaluate(request.model_dump_json())
    assert service.replay(result.model_dump_json()) == result

    plugin = M2104Plugin(service)
    token = plugin.validate(request)
    assert plugin.run(token) == result
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(ValidatedM2104Request(request, object()))


def test_replay_rejects_tampered_digest_and_public_entry_point_is_deterministic() -> None:
    request = _request()
    result = evaluate_complex_activity_external_transport(request)
    tampered = result.model_copy(update={"request_digest": "sha256:" + ("0" * 64)})

    with pytest.raises(M2104ReplayError):
        M2104Engine().replay(tampered)
    assert evaluate_complex_activity_external_transport(request) == result
