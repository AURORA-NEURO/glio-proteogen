"""Focused contract/schema smoke for provisional M10-02."""

import pytest

from glio_proteogen.contracts.m10_02 import (
    M1002_OUTPUT_MEDIA_TYPE,
    M1002_PROVISIONAL_ABI,
    RepresentationMethod,
    TransformationStep,
    contract_json_schemas,
)

_SCHEMA_COUNT = 11


def test_provisional_schemas_require_lineage_and_leakage_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["featureLineageRequired"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["leakageSafeTransformationsRequired"]
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1002_OUTPUT_MEDIA_TYPE
    assert M1002_PROVISIONAL_ABI is True


def test_fitted_transformation_requires_explicit_fit_artifact() -> None:
    with pytest.raises(ValueError, match="fit artifact"):
        TransformationStep(
            transformation_id="transform.scale",
            operation="standardize feature",
            input_feature_ids=("input.feature",),
            output_feature_ids=("output.feature",),
            fit_scope="training_only",
        )
    assert RepresentationMethod.ELASTIC_NET_CONSEQUENCE.value == "elastic_net_consequence"
