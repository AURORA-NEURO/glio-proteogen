"""Focused contract/schema smoke for provisional M11-03."""

import pytest

from glio_proteogen.contracts.m11_03 import (
    M1103_OUTPUT_MEDIA_TYPE,
    M1103_PROVISIONAL_ABI,
    MechanisticFeature,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticValueKind,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_mechanistic_safety_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["topologyInvariantsRequired"] for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["unitInvariantsRequired"] for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1103_OUTPUT_MEDIA_TYPE
    assert M1103_PROVISIONAL_ABI is True


def test_feature_lineage_and_unit_shape_are_explicit() -> None:
    lineage = MechanisticFeatureLineage(
        feature_id="pathway.activity",
        source_artifacts=(
            ArtifactReference(
                artifact_id="artifact.pathway",
                version="1.0.0",
                digest="sha256:" + "a" * 64,
                media_type="application/octet-stream",
            ),
        ),
        claim="Caller-declared pathway activity source.",
    )
    feature = MechanisticFeature(
        feature_id="pathway.activity",
        version="1.0.0",
        kind=MechanisticFeatureKind.PATHWAY,
        value_kind=MechanisticValueKind.SCALAR,
        unit="activity",
        scalar_value=0.4,
        lineage=lineage,
    )
    assert feature.lineage.complete is True
    with pytest.raises(ValueError, match="scalar feature"):
        MechanisticFeature(
            feature_id="bad",
            version="1.0.0",
            kind=MechanisticFeatureKind.STATE,
            value_kind=MechanisticValueKind.SCALAR,
            unit="state",
            lineage=lineage.model_copy(update={"feature_id": "bad"}),
        )
