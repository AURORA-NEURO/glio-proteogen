"""Focused schema and critical-signal smoke for provisional M27-05."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m27_05 import (
    M2705_M2704_INPUT_MEDIA_TYPE,
    M2705_OUTPUT_MEDIA_TYPE,
    M2705_PROVISIONAL_ABI,
    TelemetryMetricKind,
    TelemetryStatus,
    TelemetryUnit,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8
_METRIC_COUNT = 9


def test_provisional_schemas_require_critical_telemetry_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "stream",
        "sample",
        "dashboard",
        "alert",
        "reviewer-action",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["inputQualityRequired"] is True
        assert metadata["identityValidationRequired"] is True
        assert metadata["versionValidationRequired"] is True
        assert metadata["unitValidationRequired"] is True
        assert metadata["completenessValidationRequired"] is True
        assert metadata["assaySupportValidationRequired"] is True
        assert metadata["parentQualityValidationRequired"] is True
        assert metadata["quarantineUnresolvedInputs"] is True
        assert metadata["modelBehaviorRequired"] is True
        assert metadata["uncertaintyRequired"] is True
        assert metadata["uncertaintyDimensions"] == (
            "measurement",
            "sampling",
            "parameter",
            "model_form",
            "identification",
            "support",
            "transport",
        )
        assert metadata["abstentionRequired"] is True
        assert metadata["driftRequired"] is True
        assert metadata["telemetryRetentionRequired"] is True
        assert metadata["alertStateRequired"] is True
        assert metadata["criticalSignalsRetained"] is True
        assert metadata["alertDrillEvidenceRequired"] is True
        assert metadata["humanReviewCriticalDiscrepancy"] is True
        assert metadata["humanReviewNovelOodState"] is True
        assert metadata["humanReviewSupportOverride"] is True
        assert metadata["humanReviewClaimPromotion"] is True
        assert metadata["humanReviewReleaseException"] is True
        assert metadata["humanReviewBiologicalConflict"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2705_M2704_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2705_OUTPUT_MEDIA_TYPE
    assert M2705_PROVISIONAL_ABI is True


def test_telemetry_metrics_and_statuses_are_explicit() -> None:
    assert len(tuple(TelemetryMetricKind)) == _METRIC_COUNT
    assert TelemetryMetricKind.REVIEWER_ACTIONS.value == "reviewer_actions"
    assert TelemetryStatus.ABSTAINED.value == "abstained"
    assert TelemetryUnit.MILLISECONDS.value == "milliseconds"
