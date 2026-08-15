"""Focused contract/schema smoke for provisional M26-02."""

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_02 import (
    M2602_OUTPUT_MEDIA_TYPE,
    M2602_PROVISIONAL_ABI,
    LineageEdge,
    LineageRelation,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_lineage_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["immutableLineageRequired"]
        and schema["x-glio-contract"]["exactVersionTraceabilityRequired"]
        and schema["x-glio-contract"]["reproducibilityBundleRequired"]
        and schema["x-glio-contract"]["brokenLinksBlocked"]
        and schema["x-glio-contract"]["quarantineUnresolvedInputs"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2602_OUTPUT_MEDIA_TYPE
    assert M2602_PROVISIONAL_ABI is True


def test_lineage_edges_cannot_self_reference_or_omit_transform_version() -> None:
    with pytest.raises(ValidationError, match="cannot self-reference"):
        LineageEdge(
            edge_id="edge-1",
            parent_node_id="node-1",
            child_node_id="node-1",
            relation=LineageRelation.DERIVED_FROM,
        )
    with pytest.raises(ValidationError, match="require a transformation version"):
        LineageEdge(
            edge_id="edge-2",
            parent_node_id="node-1",
            child_node_id="node-2",
            relation=LineageRelation.TRANSFORMED_BY,
        )
