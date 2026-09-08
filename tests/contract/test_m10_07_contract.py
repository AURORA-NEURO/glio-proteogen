"""Focused schema and calibration-scope smoke for provisional M10-07."""

from typing import cast

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m10_07 import (
    M1007_NOMINAL_COVERAGE,
    M1007_OUTPUT_MEDIA_TYPE,
    CalibrationConfiguration,
    CalibrationEvidenceState,
    CalibrationMethod,
    CalibrationScope,
    GliomaCalibrationProgram,
    PredictionSet,
    TypedDiscordanceCalibrationObservation,
    TypedDiscordanceQuery,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_schema_inventory_is_strict_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "configuration",
        "scope",
        "estimate",
        "prediction-set",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["scopedCalibrationRequired"] is True
        assert metadata["supportThresholdRequired"] is True
        assert metadata["oodChecksRequired"] is True
        assert metadata["subgroupDisparityReviewRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["typedGliomaModelFamily"] == (
            "glioma-discordance-selective-calibration/1.0.0"
        )
        assert metadata["typedEstimator"] == "quality_weighted_damped_robust_logistic_conformal"
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1007_OUTPUT_MEDIA_TYPE


def test_calibration_scopes_and_prediction_labels_are_closed() -> None:
    scope = CalibrationScope(
        site="site-a",
        platform="platform-a",
        disease_class="glioma",
        subgroup="adult",
    )
    configuration = CalibrationConfiguration(
        configuration_id="calibration.m1007.smoke",
        version="0.1.0",
        method=CalibrationMethod.CONFORMAL,
        scopes=(scope,),
        support_threshold=0.8,
        ood_threshold=0.2,
        calibration_artifact=_artifact("artifact.calibration"),
        benchmark_artifact=_artifact("artifact.benchmark"),
    )
    prediction_set = PredictionSet(labels=("low", "high"), nominal_coverage=0.9)
    assert configuration.nominal_coverage == M1007_NOMINAL_COVERAGE
    assert prediction_set.labels == ("low", "high")


def test_typed_calibration_and_query_close_measurement_states() -> None:
    evidence = (
        EvidenceReference(
            reference=_artifact("typed"),
            role="evidence",
            claim="typed calibration evidence",
        ),
    )
    observed = TypedDiscordanceCalibrationObservation(
        observation_id="observation.typed",
        feature_id="feature.typed",
        program=GliomaCalibrationProgram.IDH_HIF1A,
        evidence_state=CalibrationEvidenceState.OBSERVED,
        protein_effect=0.8,
        rna_effect=-0.1,
        protein_standard_error=0.2,
        rna_standard_error=0.2,
        observed_label="discordant",
        subgroup="adult_glioma",
        evidence=evidence,
    )
    query = TypedDiscordanceQuery(
        feature_id="feature.query",
        program=GliomaCalibrationProgram.IDH_HIF1A,
        evidence_state=CalibrationEvidenceState.OBSERVED,
        protein_effect=0.7,
        rna_effect=0.1,
        protein_standard_error=0.2,
        rna_standard_error=0.2,
        subgroup="adult_glioma",
        evidence=evidence,
    )
    assert observed.observed_label == "discordant"
    assert query.feature_id == "feature.query"
    with pytest.raises(ValueError, match="cannot carry value"):
        TypedDiscordanceQuery(
            feature_id="feature.missing",
            evidence_state=CalibrationEvidenceState.MISSING,
            quality_weight=0.0,
            subgroup="adult_glioma",
            evidence=evidence,
            protein_effect=0.1,
        )
