"""Lightweight contract and schema gates for provisional M12-03."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m12_03 import (
    M1203_OUTPUT_MEDIA_TYPE,
    MechanisticFeature,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticValueKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 8


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1203": label}),
        media_type="application/json",
    )


def test_m1203_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"]
        for schema in schemas.values()
    )
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1203_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "biomarker_panel"
    assert metadata["topologyInvariantsRequired"]
    assert metadata["unitInvariantsRequired"]
    assert metadata["safeAbstentionRequired"]


def test_m1203_feature_requires_matching_lineage_and_one_value_shape() -> None:
    lineage = MechanisticFeatureLineage(
        feature_id="feature.pathway",
        source_artifacts=(_artifact("source"),),
        claim="Pathway feature is supported by source evidence.",
    )
    feature = MechanisticFeature(
        feature_id="feature.pathway",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit="score",
        scalar_value=0.75,
        lineage=lineage,
    )
    assert feature.lineage.feature_id == feature.feature_id

    with pytest.raises(ValueError, match="scalar feature requires"):
        MechanisticFeature(
            feature_id="feature.invalid",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.SCALAR,
            unit="score",
            lineage=MechanisticFeatureLineage(
                feature_id="feature.invalid",
                source_artifacts=(_artifact("invalid"),),
                claim="Invalid fixture.",
            ),
        )
