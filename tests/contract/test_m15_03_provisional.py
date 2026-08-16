"""Focused schema and invariant smoke for provisional M15-03."""

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m15_03 import (
    M1503_OUTPUT_MEDIA_TYPE,
    M1503_PROVISIONAL_ABI,
    FeatureKind,
    FeatureSupportStatus,
    MechanisticFeature,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7
_SOURCE_ARTIFACT = {
    "artifact_id": "source-1",
    "version": "1.0.0",
    "digest": "sha256:" + "a" * 64,
    "media_type": "application/json",
}


def test_provisional_schemas_require_feature_invariants() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "feature",
        "feature-object",
        "configuration",
        "policy",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["unitsRequired"] is True
        assert metadata["topologyInvariantsRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1503_OUTPUT_MEDIA_TYPE
    assert M1503_PROVISIONAL_ABI is True


def test_supported_feature_requires_source_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        MechanisticFeature(
            feature_id="feature-1",
            kind=FeatureKind.PATHWAY,
            label="Pathway activity",
            value="elevated",
            unit="normalized_score",
            support_status=FeatureSupportStatus.SUPPORTED,
            source_artifacts=(_SOURCE_ARTIFACT,),
        )


def test_conflicted_feature_is_not_a_negative() -> None:
    feature = MechanisticFeature(
        feature_id="feature-2",
        kind=FeatureKind.TOPOLOGY,
        label="Topology state",
        value="conflicted",
        unit="categorical",
        support_status=FeatureSupportStatus.CONFLICTED,
        source_artifacts=(_SOURCE_ARTIFACT,),
    )
    assert feature.support_status is FeatureSupportStatus.CONFLICTED
