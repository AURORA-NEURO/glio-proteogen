"""Frozen caller-declared M24-04 transport request."""

from __future__ import annotations

from evals.m24_07.fixture import artifact, context
from glio_proteogen.contracts.m24_04 import (
    EvaluateBiomarkerPanelExternalTransportRequest,
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


def _evidence(seed: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact(seed), role="evidence", claim="locked transport fixture"
        ),
    )


def _uncertainty() -> UncertaintyProfile:
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
    return EvaluateBiomarkerPanelExternalTransportRequest(
        request_id="m2404.eval.request",
        context=context(),
        mass_spectrometry_proteome=artifact("m"),
        genome_transcriptome=artifact("g"),
        ptm_annotations=artifact("p"),
        benchmark_package=artifact("b"),
        validations=tuple(
            TransportValidation(
                validation_id=f"m2404.validation.{dimension.value}",
                dimension=dimension,
                source_domain="source-domain",
                target_domain="target-domain",
                assay_or_platform="PTM-aware assay",
                specimen_description="caller-declared specimen",
                sample_count=12,
                provenance_artifact=artifact(dimension.value[0]),
                uncertainty=_uncertainty(),
                evidence=_evidence(dimension.value[0]),
            )
            for dimension in dimensions
        ),
        evaluations=tuple(
            TransportEvaluation(
                evaluation_id=f"m2404.evaluation.{dimension.value}",
                dimension=dimension,
                status=TransportStatus.SUPPORTED,
                metric_name="calibration score",
                metric_value=0.95,
                calibration_floor=0.9,
                rationale="Independent locked validation passed.",
                evidence=_evidence(dimension.value[-1]),
            )
            for dimension in dimensions
        ),
        configuration=TransportConfiguration(
            configuration_id="m2404.eval.configuration",
            version="1.0.0",
            required_dimensions=dimensions,
            minimum_calibration_floor=0.9,
        ),
        source_artifacts=(artifact("s"),),
    )
