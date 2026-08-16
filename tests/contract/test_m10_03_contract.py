"""Focused schema and locked-baseline smoke for provisional M10-03."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m10_03 import (
    M1003_BASELINE_MEDIA_TYPE,
    M1003_OUTPUT_MEDIA_TYPE,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselinePreprocessingStep,
    BaselineTuningSpec,
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
        "preprocessing",
        "tuning",
        "estimate",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["lockedPreprocessingRequired"] is True
        assert metadata["lockedTuningRequired"] is True
        assert metadata["uncertaintyRequired"] is True
        assert metadata["diagnosticsRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1003_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["formalStateInputMediaType"] == (
        M1003_BASELINE_MEDIA_TYPE
    )


def test_locked_preprocessing_tuning_and_diagnostic_smoke() -> None:
    preprocessing = BaselinePreprocessingStep(
        sequence=1,
        operation="robust-scale",
        parameters_digest=_DIGEST,
    )
    tuning = BaselineTuningSpec(
        tuning_id="tuning.m1003.smoke",
        protocol="locked-five-fold",
        objective="mean absolute error",
        folds=5,
        benchmark_artifact=_artifact("artifact.benchmark"),
    )
    diagnostic = BaselineDiagnostic(
        diagnostic_id="diagnostic.m1003.smoke",
        status=BaselineDiagnosticStatus.PASS,
        metric_name="reproduction_error",
        metric_value=0.1,
        message="Published baseline behavior is reproducible in the fixture.",
    )
    assert preprocessing.locked is True
    assert tuning.locked is True
    assert diagnostic.status is BaselineDiagnosticStatus.PASS
