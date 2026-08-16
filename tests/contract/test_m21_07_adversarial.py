"""Deep adversarial closure for M21-07 result and operational invariants."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m21_07 import (
    ComplexActivityHumanFactorsResult,
    EvaluationStatus,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalDimension,
    OperationalStatus,
)
from glio_proteogen.contracts.m21_07.canonical import result_payload_digest
from glio_proteogen.modules.c21_reference_material.m21_07_human_factors_operational_evaluator import (  # noqa: E501
    M2107Engine,
    M2107ReplayError,
)
from tests.contract.test_m21_07_hardening import _fallback, _metric, _request


def test_request_metrics_sources_and_configuration_cannot_repeat_entries() -> None:
    request = _request()
    duplicate_metrics = (*request.metrics, request.metrics[0])
    with pytest.raises(ValidationError, match="metric ids"):
        type(request).model_validate(request.model_copy(update={"metrics": duplicate_metrics}))
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": request.source_artifacts * 2})
        )
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        type(request.configuration).model_validate(
            request.configuration.model_copy(
                update={"required_dimensions": (OperationalDimension.REVIEWER_COMPREHENSION,) * 7}
            )
        )


def test_fallback_and_report_collections_are_closed() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="unavailable fallback"):
        FallbackScenario.model_validate(
            _fallback().model_copy(update={"fallback_available": False})
        )
    result = M2107Engine().evaluate(request)
    assert result.report is not None
    report = result.report
    duplicate_metric = report.metrics[0].model_copy(update={"metric_id": "metric.duplicate"})
    with pytest.raises(ValidationError, match="metric ids"):
        HumanFactorsOperationalReport.model_validate(
            report.model_copy(update={"metrics": (duplicate_metric, duplicate_metric)})
        )
    with pytest.raises(ValidationError, match="every configured"):
        HumanFactorsOperationalReport.model_validate(
            report.model_copy(update={"metrics": report.metrics[:-1]})
        )


def test_result_identifier_evidence_findings_and_report_closure_are_immutable() -> None:
    result = M2107Engine().evaluate(_request())
    adapter = TypeAdapter(ComplexActivityHumanFactorsResult)
    with pytest.raises(ValidationError, match="result id"):
        adapter.validate_python(
            result.model_copy(update={"result_id": "result.forged"}), strict=True
        )
    with pytest.raises(ValidationError, match="result evidence"):
        adapter.validate_python(
            result.model_copy(update={"evidence": result.evidence * 2}), strict=True
        )
    finding = result.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        adapter.validate_python(
            result.model_copy(update={"findings": (finding, finding)}), strict=True
        )
    report = result.report
    assert report is not None
    with pytest.raises(ValidationError, match="configuration must equal"):
        adapter.validate_python(
            result.model_copy(
                update={
                    "report": report.model_copy(
                        update={
                            "configuration": report.configuration.model_copy(
                                update={"version": "2.0.0"}
                            )
                        }
                    )
                }
            ),
            strict=True,
        )
    invalid_report = HumanFactorsOperationalReport.model_construct(
        report_id=report.report_id,
        version=report.version,
        metrics=report.metrics[:-1],
        fallbacks=report.fallbacks,
        configuration=report.configuration,
        locked=True,
        evidence=report.evidence,
    )
    invalid_result = result.model_copy(update={"report": invalid_report})
    with pytest.raises(ValueError, match="metrics must equal"):
        invalid_result.result_is_closed()
    with pytest.raises(ValidationError, match="abstained result"):
        adapter.validate_python(
            result.model_copy(
                update={
                    "status": EvaluationStatus.ABSTAINED,
                    "report": None,
                    "abstention_reason": None,
                }
            ),
            strict=True,
        )


def test_replay_rejects_each_canonical_tamper_and_expected_mismatch() -> None:
    engine = M2107Engine()
    result = engine.evaluate(_request())
    with pytest.raises(M2107ReplayError):
        engine.replay({})  # type: ignore[arg-type]
    for candidate in (
        result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
        result.model_copy(update={"result_id": "result.forged"}),
        result.model_copy(update={"result_digest": "sha256:" + "f" * 64}),
    ):
        with pytest.raises(M2107ReplayError):
            engine.replay(candidate)
    mismatch = result.model_copy(update={"human_review_required": False})
    mismatch = mismatch.model_copy(update={"result_digest": result_payload_digest(mismatch)})
    with pytest.raises(M2107ReplayError):
        engine.replay(mismatch)


def test_preflight_and_metric_status_boundaries_fail_closed() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(ValueError, match="requires accepted configuration"):
        M2107Engine().evaluate(Hostile())
    metric = _metric(OperationalDimension.THROUGHPUT)
    assert metric.status is OperationalStatus.PASS
