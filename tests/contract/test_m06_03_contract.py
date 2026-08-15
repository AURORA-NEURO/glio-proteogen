"""Lightweight checks for the provisional M06-03 contract spine."""

from glio_proteogen.contracts.m06_03 import (
    M0603_MAX_EVIDENCE,
    M0603_OUTPUT_MEDIA_TYPE,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselineEstimatorFamily,
    BaselinePreprocessingPolicy,
    BaselineTuningRecord,
    MatureBaselineConfiguration,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 7
_SEED = 7
_ESTIMATE_VALUE = 1.25


def _reference() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="reference." + "a" * 64,
        version="0.1.0",
        digest="sha256:" + "b" * 64,
        media_type="application/json",
    )


def test_locked_baseline_configuration_binds_preprocessing_and_tuning() -> None:
    preprocessing = BaselinePreprocessingPolicy(
        policy_id="policy.baseline",
        version="0.1.0",
        operations=("unit-normalize",),
    )
    tuning = BaselineTuningRecord(
        tuning_id="tuning.baseline",
        version="0.1.0",
        method="locked-reference-grid",
        objective="minimize locked validation loss",
        seed=_SEED,
    )
    configuration = MatureBaselineConfiguration(
        configuration_id="configuration.baseline",
        version="0.1.0",
        estimator_family=BaselineEstimatorFamily.ROBUST_STATISTICAL,
        state_schema_id="schema.formal-state",
        state_schema_version="0.1.0",
        preprocessing=preprocessing,
        tuning=tuning,
        reference=_reference(),
    )
    assert configuration.locked is True
    assert configuration.preprocessing.locked is True
    assert configuration.tuning.locked is True


def test_scalar_baseline_estimate_is_explicitly_typed() -> None:
    estimate = BaselineEstimate(
        feature_id="protein.abundance",
        kind=BaselineEstimateKind.SCALAR,
        unit="normalized-abundance",
        estimate_value=_ESTIMATE_VALUE,
    )
    assert estimate.estimate_value == _ESTIMATE_VALUE


def test_schema_exports_are_provisional_and_bounded() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0603_OUTPUT_MEDIA_TYPE
    assert M0603_MAX_EVIDENCE > 0
