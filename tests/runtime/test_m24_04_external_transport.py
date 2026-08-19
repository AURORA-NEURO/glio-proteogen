"""Runtime, replay and interface tests for provisional M24-04."""

from __future__ import annotations

import json

import pytest
from evals.m24_07.fixture import artifact, context

from glio_proteogen.contracts.m24_04 import (
    EvaluateBiomarkerPanelExternalTransportRequest,
    EvaluationStatus,
    TransportConfiguration,
    TransportDimension,
    TransportEvaluation,
    TransportStatus,
    TransportValidation,
)
from glio_proteogen.kernel.models import (
    EstimateState,
    EvidenceReference,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c21_reference_material import (
    m24_04_external_transport_evaluator as m2404,
)


def evidence(seed: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact(seed), role="evidence", claim="locked transport fixture"
        ),
    )


def uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.5,
        rationale="Caller-declared transport uncertainty.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def request() -> EvaluateBiomarkerPanelExternalTransportRequest:
    dimensions = tuple(TransportDimension)
    validations = tuple(
        TransportValidation(
            validation_id=f"m2404.validation.{dimension.value}",
            dimension=dimension,
            source_domain="source-domain",
            target_domain="target-domain",
            assay_or_platform="PTM-aware assay",
            specimen_description="caller-declared specimen",
            sample_count=12,
            provenance_artifact=artifact(dimension.value[0]),
            uncertainty=uncertainty(),
            evidence=evidence(dimension.value[0]),
        )
        for dimension in dimensions
    )
    evaluations = tuple(
        TransportEvaluation(
            evaluation_id=f"m2404.evaluation.{dimension.value}",
            dimension=dimension,
            status=TransportStatus.SUPPORTED,
            metric_name="calibration score",
            metric_value=0.95,
            calibration_floor=0.9,
            rationale="Independent locked validation passed.",
            evidence=evidence(dimension.value[-1]),
        )
        for dimension in dimensions
    )
    return EvaluateBiomarkerPanelExternalTransportRequest(
        request_id="m2404.test.request",
        context=context(),
        mass_spectrometry_proteome=artifact("m"),
        genome_transcriptome=artifact("g"),
        ptm_annotations=artifact("p"),
        benchmark_package=artifact("b"),
        validations=validations,
        evaluations=evaluations,
        configuration=TransportConfiguration(
            configuration_id="m2404.test.configuration",
            version="1.0.0",
            required_dimensions=dimensions,
            minimum_calibration_floor=0.9,
        ),
        source_artifacts=(artifact("s"),),
    )


def test_supported_transport_result_replays_deterministically() -> None:
    service = m2404.M2404Service()
    first = service.evaluate(request())
    second = service.evaluate(json.dumps(request().model_dump(mode="json"), sort_keys=True))
    assert first.status is EvaluationStatus.EVALUATED
    assert first.report is not None
    assert first.report.support_domain.retained_dimensions == tuple(TransportDimension)
    assert first.result_digest == second.result_digest
    assert service.verify_replay(first).result_digest == first.result_digest


def test_domain_narrowing_abstains_without_report() -> None:
    typed = request()
    narrowed = typed.evaluations[0].model_copy(
        update={
            "status": TransportStatus.DOMAIN_NARROWED,
            "metric_value": 0.5,
            "rationale": "Calibration floor failed; domain narrowed.",
        }
    )
    changed = typed.model_copy(update={"evaluations": (narrowed, *typed.evaluations[1:])})
    result = m2404.M2404Service().evaluate(changed)
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.support_decision.status.value == "review_required"
    assert result.findings


def test_replay_rejects_self_rehashed_evaluation_and_denied_control() -> None:
    service = m2404.M2404Service()
    result = service.evaluate(request())
    assert result.report is not None
    changed = result.report.evaluations[0].model_copy(update={"metric_value": 0.91})
    forged_report = result.report.model_copy(
        update={"evaluations": (changed, *result.report.evaluations[1:])}
    )
    forged = result.model_copy(update={"report": forged_report})
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result.result_digest}
    )
    with pytest.raises(m2404.M2404ReplayError):
        service.verify_replay(forged)
    denied_support = request().context.references.support.model_copy(update={"state": "rejected"})
    denied = request().model_copy(
        update={
            "context": request().context.model_copy(
                update={
                    "references": request().context.references.model_copy(
                        update={"support": denied_support}
                    )
                }
            )
        }
    )
    with pytest.raises(m2404.AuthorizationError):
        service.evaluate(denied)


def test_plugin_tokens_are_instance_bound_and_snapshot_bound() -> None:
    first = m2404.M2404Plugin(m2404.M2404Service())
    second = m2404.M2404Plugin(m2404.M2404Service())
    token = first.validate(m2404.ExternalTransportSubmission(request()))

    assert first.run(token).status is EvaluationStatus.EVALUATED
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)

    forged = m2404.ValidatedM2404Request(token.request, object())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(forged)

    mutated = first.validate(m2404.ExternalTransportSubmission(request()))
    object.__setattr__(mutated.request, "request_id", "m2404.forged.request")
    with pytest.raises(TypeError, match="validated request token"):
        first.run(mutated)

    replaced = first.validate(m2404.ExternalTransportSubmission(request()))
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(replaced)
