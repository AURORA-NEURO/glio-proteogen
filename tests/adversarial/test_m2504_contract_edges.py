"""Additional branch closure for M25-04 contract and replay guards."""

from __future__ import annotations

import pytest
from evals.m25_04.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m25_04 import (
    EvaluationStatus,
    ProteotypeExternalTransportResult,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    canonical_request_digest,
    normalized_request,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference, SemanticVersion
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504ReplayError,
    M2504Service,
)


def _evidence() -> tuple[EvidenceReference, ...]:
    artifact = ArtifactReference(
        artifact_id="m2504.edge.evidence",
        version=SemanticVersion("1.0.0"),
        digest="sha256:" + ("d" * 64),
        media_type="application/octet-stream",
    )
    return (EvidenceReference(reference=artifact, role="evidence", claim="edge evidence"),)


def _valid_dimensions() -> tuple[TransportDimension, ...]:
    return tuple(TransportDimension)


def test_canonical_mapping_projection_is_supported() -> None:
    value = {"request_id": "mapping"}
    assert normalized_request(value) == value
    assert canonical_request_digest(value).startswith("sha256:")


def test_domain_narrowed_metric_must_fail_floor() -> None:
    with pytest.raises(ValidationError, match="calibration floor"):
        TransportEvaluation(
            evaluation_id="m2504.edge.narrowed",
            dimension=TransportDimension.SITE,
            status=TransportStatus.DOMAIN_NARROWED,
            metric_name="score",
            metric_value=0.9,
            calibration_floor=0.8,
            rationale="Contradictory narrowed declaration.",
            evidence=_evidence(),
        )


def test_support_domain_overlap_is_rejected() -> None:
    with pytest.raises(ValidationError, match="disjoint"):
        SupportDomainUpdate(
            update_id="m2504.edge.overlap",
            version=SemanticVersion("1.0.0"),
            status=TransportStatus.DOMAIN_NARROWED,
            retained_dimensions=_valid_dimensions(),
            narrowed_dimensions=(TransportDimension.SITE,),
            rationale="Overlapping support declaration.",
            evidence=_evidence(),
        )


def test_supported_domain_cannot_have_narrowed_dimensions() -> None:
    with pytest.raises(ValidationError, match="supported domain"):
        SupportDomainUpdate(
            update_id="m2504.edge.supported-narrowed",
            version=SemanticVersion("1.0.0"),
            status=TransportStatus.SUPPORTED,
            retained_dimensions=tuple(
                item for item in _valid_dimensions() if item is not TransportDimension.SITE
            ),
            narrowed_dimensions=(TransportDimension.SITE,),
            rationale="Contradictory support declaration.",
            evidence=_evidence(),
        )


def test_narrowed_domain_requires_a_narrowed_dimension() -> None:
    with pytest.raises(ValidationError, match="narrowed domain"):
        SupportDomainUpdate(
            update_id="m2504.edge.narrowed-empty",
            version=SemanticVersion("1.0.0"),
            status=TransportStatus.DOMAIN_NARROWED,
            retained_dimensions=_valid_dimensions(),
            rationale="Missing narrowed dimension.",
            evidence=_evidence(),
        )


def test_configuration_duplicate_and_incomplete_dimensions_are_rejected() -> None:
    request = build_request()
    duplicate = request.configuration.model_copy(
        update={"required_dimensions": (*_valid_dimensions(), TransportDimension.SITE)}
    )
    incomplete = request.configuration.model_copy(
        update={"required_dimensions": _valid_dimensions()[:-1]}
    )
    with pytest.raises(ValidationError, match="unique"):
        type(request.configuration).model_validate(duplicate.model_dump(mode="python"))
    with pytest.raises(ValidationError, match="all seven"):
        type(request.configuration).model_validate(incomplete.model_dump(mode="python"))


def test_report_missing_and_duplicate_dimensions_are_rejected() -> None:
    result = M2504Service().execute(build_request())
    assert result.report is not None
    report = result.report
    missing_validation = report.model_dump(mode="python")
    missing_validation["validations"] = report.validations[:-1]
    missing_evaluation = report.model_dump(mode="python")
    missing_evaluation["evaluations"] = report.evaluations[:-1]
    duplicate_validation = report.model_dump(mode="python")
    duplicate_validation["validations"] = (
        report.validations[0],
        report.validations[0],
        *report.validations[1:],
    )
    duplicate_evaluation = report.model_dump(mode="python")
    duplicate_evaluation["evaluations"] = (
        report.evaluations[0],
        report.evaluations[0],
        *report.evaluations[1:],
    )
    with pytest.raises(ValidationError, match="validate every"):
        TransportabilityReport.model_validate(missing_validation, strict=True)
    with pytest.raises(ValidationError, match="evaluate every"):
        TransportabilityReport.model_validate(missing_evaluation, strict=True)
    with pytest.raises(ValidationError, match="validation dimensions"):
        TransportabilityReport.model_validate(duplicate_validation, strict=True)
    with pytest.raises(ValidationError, match="evaluation dimensions"):
        TransportabilityReport.model_validate(duplicate_evaluation, strict=True)


def test_supported_report_cannot_narrow_support_domain() -> None:
    result = M2504Service().execute(build_request())
    assert result.report is not None
    support_data = result.report.support_domain.model_dump(mode="python")
    support_data.update(
        {
            "status": TransportStatus.SUPPORTED,
            "retained_dimensions": tuple(
                item for item in _valid_dimensions() if item is not TransportDimension.SITE
            ),
            "narrowed_dimensions": (TransportDimension.SITE,),
        }
    )
    support = result.report.support_domain.model_construct(**support_data)
    invalid_report = result.report.model_copy(update={"support_domain": support})
    with pytest.raises(ValueError, match="supported report"):
        invalid_report.report_is_closed()  # type: ignore[operator]


def test_request_context_and_configuration_boundaries_are_rejected() -> None:
    request = build_request()
    context_data = request.model_dump(mode="python")
    context_data["context"]["request_id"] = "m2504.other-request"
    configuration_data = request.configuration.model_dump(mode="python")
    configuration_data["required_dimensions"] = _valid_dimensions()[:-1]
    bad_configuration = request.configuration.model_construct(**configuration_data)
    configuration_data = request.model_dump(mode="python")
    configuration_data["configuration"] = bad_configuration
    with pytest.raises(ValidationError, match="context request id"):
        type(request).model_validate(context_data, strict=True)
    with pytest.raises(ValidationError, match="all seven"):
        type(request).model_validate(configuration_data, strict=True)


def test_result_evaluated_requires_report() -> None:
    result = M2504Service().execute(build_request())
    data = result.model_dump(mode="python")
    data["report"] = None
    with pytest.raises(ValidationError, match="evaluated result"):
        ProteotypeExternalTransportResult.model_validate(data, strict=True)


def test_result_abstained_requires_safe_empty_report() -> None:
    result = M2504Service().execute(build_request())
    data = result.model_dump(mode="python")
    data["status"] = EvaluationStatus.ABSTAINED
    with pytest.raises(ValidationError, match="abstained result"):
        ProteotypeExternalTransportResult.model_validate(data, strict=True)


def test_result_context_request_id_is_closed() -> None:
    result = M2504Service().execute(build_request())
    bad_context = result.request.context.model_copy(update={"request_id": "m2504.other"})
    bad_request = result.request.model_copy(update={"context": bad_context})
    tampered = result.model_copy(
        update={
            "request": bad_request,
            "request_digest": canonical_request_digest(bad_request),
        }
    )
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises(ValueError, match="result request context id"):
        tampered.result_is_closed()  # type: ignore[operator]


def test_result_provenance_module_is_closed() -> None:
    result = M2504Service().execute(build_request())
    provenance = result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M99-99"})
    tampered = result.model_copy(update={"provenance": provenance})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises(ValidationError, match="provenance"):
        ProteotypeExternalTransportResult.model_validate(tampered.model_dump(mode="python"))


def test_replay_request_id_guard_is_closed() -> None:
    service = M2504Service()
    result = service.execute(build_request())
    bad_context = result.request.context.model_copy(update={"request_id": "m2504.other"})
    bad_request = result.request.model_construct(context=bad_context)  # type: ignore[call-arg]
    tampered = result.model_copy(
        update={
            "request": bad_request,
            "request_digest": canonical_request_digest(bad_request),
        }
    )
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises((M2504ReplayError, ValidationError)):
        service.verify_replay(tampered)
