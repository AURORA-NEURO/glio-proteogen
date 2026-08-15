"""Lightweight contract and schema gates for provisional M14-03."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m14_03 import (
    M1403_DOSSIER_SLICE,
    M1403_OUTPUT_MEDIA_TYPE,
    M1403_REQUIREMENT_SHA256,
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
        digest=sha256_digest({"m1403": label}),
        media_type="application/json",
    )


def test_m1403_schemas_are_strict_and_explicitly_provisional() -> None:
    schemas = contract_json_schemas()

    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["pendingOwnerConfirmation"]
        for schema in schemas.values()
    )
    metadata = schemas["output"]["x-glio-contract"]
    assert metadata["outputMediaType"] == M1403_OUTPUT_MEDIA_TYPE
    assert metadata["parentTarget"] == "protein_subtype"
    assert metadata["stoichiometricInvariantsRequired"]
    assert metadata["topologyInvariantsRequired"]
    assert metadata["unitInvariantsRequired"]
    assert metadata["safeAbstentionRequired"]
    assert metadata["dossierSlice"] == M1403_DOSSIER_SLICE == "4804-4847"
    assert metadata["requirementSha256"] == M1403_REQUIREMENT_SHA256


def test_m1403_feature_requires_matching_lineage_and_one_value_shape() -> None:
    lineage = MechanisticFeatureLineage(
        feature_id="feature.complex",
        source_artifacts=(_artifact("source"),),
        claim="Complex feature is supported by source evidence.",
    )
    feature = MechanisticFeature(
        feature_id="feature.complex",
        version="1.0.0",
        kind=MechanisticFeatureKind.TOPOLOGY,
        value_kind=MechanisticValueKind.SCALAR,
        unit="stoichiometric_ratio",
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
            unit="stoichiometric_ratio",
            lineage=MechanisticFeatureLineage(
                feature_id="feature.invalid",
                source_artifacts=(_artifact("invalid"),),
                claim="Invalid fixture.",
            ),
        )
