"""Strict contract/schema smoke for the provisional M06-07 scaffold."""

from __future__ import annotations

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m06_07 import (
    M0607_OUTPUT_MEDIA_TYPE,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrationStratum,
    CalibrationStratumDimension,
    OutOfDistributionStatus,
    SelectivePredictionStatus,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    M0607CalibrationEngine,
    M0607Service,
)

_EXPECTED_COVERAGE = 0.90
_EXPECTED_ERROR = 0.02


def test_schema_inventory_is_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "policy",
        "stratum",
        "threshold",
        "estimate",
        "prediction-set",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
        assert metadata["calibrationMetricsFrozen"] is False
        assert metadata["coverageCeilingsFrozen"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0607_OUTPUT_MEDIA_TYPE


def test_calibration_selective_prediction_and_runtime_import_smoke() -> None:
    stratum = CalibrationStratum(
        stratum_id="stratum.m0607.site",
        dimension=CalibrationStratumDimension.SITE,
        label="site-a",
        sample_count=10,
        observed_coverage=_EXPECTED_COVERAGE,
        calibration_error=_EXPECTED_ERROR,
    )
    prediction_set = CalibratedPredictionSet(
        prediction_set_id="prediction-set.m0607.smoke",
        feature_id="feature.m0607.smoke",
        labels=("high", "low"),
        target_coverage=_EXPECTED_COVERAGE,
        observed_coverage=_EXPECTED_COVERAGE,
    )
    estimate = CalibratedEstimate(
        feature_id="feature.m0607.smoke",
        estimate_value=1.0,
        prediction_set_id=prediction_set.prediction_set_id,
        support_score=0.95,
        ood_status=OutOfDistributionStatus.IN_DOMAIN,
        calibration_error=_EXPECTED_ERROR,
        selection_status=SelectivePredictionStatus.SELECTED,
    )
    assert stratum.observed_coverage == _EXPECTED_COVERAGE
    assert estimate.prediction_set_id == prediction_set.prediction_set_id
    assert canonical_request_digest({"stratum": stratum.model_dump(mode="json")}).startswith(
        "sha256:"
    )
    assert M0607Service is not None
    assert M0607CalibrationEngine is not None
