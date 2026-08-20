"""Deep adversarial closure for M21-04 result and transport boundaries."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m21_04 import (
    ComplexActivityExternalTransportResult,
    EvaluationStatus,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportDimension,
    TransportStatus,
    normalized_request,
    result_payload_digest,
)
from glio_proteogen.modules.c21_reference_material.m21_04_external_transport_evaluator import (
    M2104Engine,
    M2104ReplayError,
)
from tests.contract.test_m21_04_hardening import _evaluation, _request


def test_request_source_and_evaluation_collections_cannot_repeat_entries() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": request.source_artifacts * 2})
        )
    duplicate = (*request.evaluations, request.evaluations[0])
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        type(request).model_validate(request.model_copy(update={"evaluations": duplicate}))


def test_request_and_report_closures_reject_missing_or_duplicate_dimensions() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="required transport dimensions must be unique"):
        type(request.configuration).model_validate(
            request.configuration.model_copy(
                update={"required_dimensions": (TransportDimension.SITE,) * 2}
            )
        )
    with pytest.raises(ValidationError, match="context request id"):
        type(request).model_validate(request.model_copy(update={"request_id": "request.other"}))
    result = M2104Engine().evaluate(request)
    assert result.report is not None
    report = result.report
    with pytest.raises(ValidationError, match="validate every configured"):
        TransportabilityReport.model_validate(
            report.model_copy(update={"validations": report.validations[:-1]})
        )
    with pytest.raises(ValidationError, match="evaluate every configured"):
        TransportabilityReport.model_validate(
            report.model_copy(update={"evaluations": report.evaluations[:-1]})
        )
    duplicate = (*report.evaluations, report.evaluations[0])
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        TransportabilityReport.model_validate(report.model_copy(update={"evaluations": duplicate}))


def test_validation_dimensions_are_unique_and_exactly_configured() -> None:
    request = _request()
    duplicate = (*request.validations, request.validations[0])
    with pytest.raises(ValidationError, match="validation dimensions"):
        type(request).model_validate(request.model_copy(update={"validations": duplicate}))

    reduced = request.model_copy(
        update={
            "configuration": request.configuration.model_copy(
                update={"required_dimensions": (TransportDimension.SITE,)}
            )
        }
    )
    with pytest.raises(ValidationError, match="validation dimensions"):
        type(request).model_validate(reduced)

    result = M2104Engine().evaluate(request)
    assert result.report is not None
    with pytest.raises(ValidationError, match="validation dimensions"):
        TransportabilityReport.model_validate(
            result.report.model_copy(
                update={"validations": (*result.report.validations, result.report.validations[0])}
            )
        )


def test_supported_and_narrowed_statuses_require_the_declared_floor() -> None:
    supported = _evaluation(TransportDimension.SITE)
    with pytest.raises(ValidationError, match="supported evaluation"):
        type(supported).model_validate(supported.model_copy(update={"metric_value": 0.1}))
    narrowed = _evaluation(TransportDimension.SITE, TransportStatus.DOMAIN_NARROWED)
    with pytest.raises(ValidationError, match="narrowed evaluation"):
        type(narrowed).model_validate(
            narrowed.model_copy(update={"metric_value": narrowed.calibration_floor})
        )


def test_support_domain_cannot_overlap_or_drop_dimensions() -> None:
    request = _request()
    result = M2104Engine().evaluate(request)
    assert result.report is not None
    support = result.report.support_domain
    with pytest.raises(ValidationError, match="disjoint"):
        SupportDomainUpdate.model_validate(
            support.model_copy(update={"narrowed_dimensions": (TransportDimension.SITE,)})
        )
    with pytest.raises(ValidationError, match="close every configured"):
        TransportabilityReport.model_validate(
            result.report.model_copy(
                update={
                    "support_domain": support.model_copy(
                        update={"retained_dimensions": support.retained_dimensions[:-1]}
                    )
                }
            )
        )


def test_result_digest_identifier_and_request_binding_are_immutable() -> None:
    result = M2104Engine().evaluate(_request())
    adapter = TypeAdapter(ComplexActivityExternalTransportResult)
    for field, value, message in (
        ("request_digest", "sha256:" + "f" * 64, "request digest"),
        ("result_id", "result.forged", "result id"),
        ("result_digest", "sha256:" + "f" * 64, "result digest"),
    ):
        with pytest.raises(ValidationError, match=message):
            adapter.validate_python(result.model_copy(update={field: value}), strict=True)
    report = result.report
    assert report is not None
    with pytest.raises(ValidationError, match="supported transport report"):
        adapter.validate_python(result.model_copy(update={"report": None}), strict=True)
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
    invalid_report = TransportabilityReport.model_construct(
        report_id=report.report_id,
        version=report.version,
        validations=report.validations[:-1],
        evaluations=report.evaluations,
        support_domain=report.support_domain,
        configuration=report.configuration,
        locked=True,
        evidence=report.evidence,
    )
    invalid_result = result.model_copy(update={"report": invalid_report})
    with pytest.raises(ValueError, match="validations must equal"):
        invalid_result.result_is_closed()
    invalid_report = TransportabilityReport.model_construct(
        report_id=report.report_id,
        version=report.version,
        validations=report.validations,
        evaluations=report.evaluations[:-1],
        support_domain=report.support_domain,
        configuration=report.configuration,
        locked=True,
        evidence=report.evidence,
    )
    invalid_result = result.model_copy(update={"report": invalid_report})
    with pytest.raises(ValueError, match="evaluations must equal"):
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


def test_result_evidence_and_finding_ids_remain_unique() -> None:
    result = M2104Engine().evaluate(_request())
    adapter = TypeAdapter(ComplexActivityExternalTransportResult)
    with pytest.raises(ValidationError, match="result evidence"):
        adapter.validate_python(
            result.model_copy(update={"evidence": result.evidence * 2}), strict=True
        )
    finding = result.findings[0]
    with pytest.raises(ValidationError, match="finding ids"):
        adapter.validate_python(
            result.model_copy(update={"findings": (finding, finding)}), strict=True
        )


def test_replay_rejects_non_result_and_canonical_tampering() -> None:
    engine = M2104Engine()
    with pytest.raises(M2104ReplayError):
        engine.replay({})  # type: ignore[arg-type]
    result = engine.evaluate(_request())
    tampered = result.model_copy(update={"evidence": ()})
    with pytest.raises(M2104ReplayError):
        engine.replay(tampered)
    wrong_id = result.model_copy(update={"result_id": "result.forged"})
    with pytest.raises(M2104ReplayError):
        engine.replay(wrong_id)
    wrong_digest = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises(M2104ReplayError):
        engine.replay(wrong_digest)
    expected_mismatch = result.model_copy(update={"human_review_required": False})
    expected_mismatch = expected_mismatch.model_copy(
        update={"result_digest": result_payload_digest(expected_mismatch)}
    )
    with pytest.raises(M2104ReplayError):
        engine.replay(expected_mismatch)


def test_preflight_fails_closed_for_hostile_mapping_shapes() -> None:
    with pytest.raises(ValueError, match="requires accepted configuration"):
        M2104Engine().evaluate({"context": {"references": None}})

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(ValueError, match="requires accepted configuration"):
        M2104Engine().evaluate(Hostile())


def test_canonical_mapping_projection_is_supported() -> None:
    request = _request()
    assert normalized_request(request.model_dump(mode="json"))["request_id"] == request.request_id
