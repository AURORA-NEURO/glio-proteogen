"""Runtime/replay/service tests for provisional M25-04."""

from __future__ import annotations

import pytest
from evals.m25_04.fixture import build_request, denied_request, not_evaluable_request

from glio_proteogen.contracts.m25_04 import EvaluationStatus, TransportDimension, TransportStatus
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504AuthorizationError,
    M2504ReplayError,
    M2504Service,
)


def test_supported_transport_report_is_deterministic_and_replayable() -> None:
    service = M2504Service()
    result = service.execute(build_request())
    repeated = service.execute(build_request())

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.status is TransportStatus.SUPPORTED
    assert result.support_decision.status.value == "supported"
    assert result.result_digest == repeated.result_digest
    assert service.verify_replay(result).result_digest == result.result_digest


def test_narrowed_transport_preserves_limited_support_and_finding() -> None:
    result = M2504Service().execute(build_request(status=TransportStatus.DOMAIN_NARROWED))

    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.report.support_domain.status is TransportStatus.DOMAIN_NARROWED
    assert result.support_decision.status.value == "limited"
    assert result.findings
    assert result.report.support_domain.narrowed_dimensions == (TransportDimension.SITE,)


def test_not_evaluable_transport_abstains_without_report() -> None:
    result = M2504Service().execute(not_evaluable_request())

    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status.value == "review_required"


def test_denied_controls_fail_closed_before_evaluation() -> None:
    with pytest.raises(M2504AuthorizationError):
        M2504Service().execute(denied_request())


def test_tampered_result_digest_is_rejected() -> None:
    service = M2504Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})

    with pytest.raises((M2504ReplayError, ValueError)):
        service.verify_replay(tampered)
