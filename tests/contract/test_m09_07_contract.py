"""Focused schema and calibration-scope smoke for provisional M09-07."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m09_07 import (
    M0907_NOMINAL_COVERAGE,
    M0907_OUTPUT_MEDIA_TYPE,
    CalibrationConfiguration,
    CalibrationMethod,
    CalibrationScope,
    PredictionSet,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

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
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0907_OUTPUT_MEDIA_TYPE


def test_calibration_scopes_and_prediction_labels_are_closed() -> None:
    scope = CalibrationScope(
        site="site-a",
        platform="platform-a",
        disease_class="glioma",
        subgroup="adult",
    )
    configuration = CalibrationConfiguration(
        configuration_id="calibration.m0907.smoke",
        version="0.1.0",
        method=CalibrationMethod.CONFORMAL,
        scopes=(scope,),
        support_threshold=0.8,
        ood_threshold=0.2,
        calibration_artifact=_artifact("artifact.calibration"),
        benchmark_artifact=_artifact("artifact.benchmark"),
    )
    prediction_set = PredictionSet(labels=("low", "high"), nominal_coverage=0.9)
    assert configuration.nominal_coverage == M0907_NOMINAL_COVERAGE
    assert prediction_set.labels == ("low", "high")
