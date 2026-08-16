"""Focused contract/schema smoke for provisional M26-02."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_02 import (
    M2602_OUTPUT_MEDIA_TYPE,
    M2602_PROVISIONAL_ABI,
    M2602_REQUIRED_NODE_KINDS,
    M2602_UPSTREAM_MEDIA_TYPE,
    LineageEdge,
    LineageGraph,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    ReproducibilityBundle,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_lineage_controls() -> None:
    schemas = contract_json_schemas()
    metadata = tuple(
        cast("dict[str, Any]", schema["x-glio-contract"]) for schema in schemas.values()
    )
    assert len(schemas) == _SCHEMA_COUNT
    assert all(item["provisionalAbi"] for item in metadata)
    assert all(item["pendingOwnerConfirmation"] for item in metadata)
    assert all(
        item["immutableLineageRequired"]
        and item["exactVersionTraceabilityRequired"]
        and item["reproducibilityBundleRequired"]
        and item["brokenLinksBlocked"]
        and item["quarantineUnresolvedInputs"]
        and item["explicitAbstentionRequired"]
        and item["unsupportedToNegative"] is False
        for item in metadata
    )
    assert all(item["parentTarget"] == "protein subtype" for item in metadata)
    output_metadata = cast("dict[str, Any]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M2602_OUTPUT_MEDIA_TYPE
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


def _artifact(name: str, version: str = "1.0.0") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version=version,
        digest="sha256:" + (name.encode().hex() * 64)[:64],
        media_type="application/json",
    )


def _nodes() -> tuple[LineageNode, ...]:
    return tuple(
        LineageNode(
            node_id=f"node-{index}",
            kind=kind,
            name=f"{kind.value}-artifact",
            version="1.0.0",
            artifact=_artifact(f"artifact-{index}"),
            producer=f"producer-{index}",
            node_digest="sha256:" + (f"{index:02x}" * 32),
        )
        for index, kind in enumerate(LineageNodeKind, start=1)
    )


def test_required_node_kind_cardinality_is_closed() -> None:
    assert len(LineageNodeKind) == M2602_REQUIRED_NODE_KINDS
    bundle = ReproducibilityBundle(
        bundle_id="bundle-1",
        version="1.0.0",
        root_node_ids=("node-1",),
        required_kinds=tuple(LineageNodeKind),
        graph_digest="sha256:" + "a" * 64,
        environment_digest="sha256:" + "b" * 64,
    )
    assert bundle.locked is True
    with pytest.raises(ValidationError, match="at least 7 item"):
        ReproducibilityBundle(
            bundle_id="bundle-2",
            version="1.0.0",
            root_node_ids=("node-1",),
            required_kinds=tuple(LineageNodeKind)[:-1],
            graph_digest="sha256:" + "a" * 64,
            environment_digest="sha256:" + "b" * 64,
        )


def test_node_versions_and_graph_cycles_cannot_be_silently_accepted() -> None:
    with pytest.raises(ValidationError, match="version must match"):
        LineageNode(
            node_id="node-version",
            kind=LineageNodeKind.MODEL,
            name="model",
            version="2.0.0",
            artifact=_artifact("artifact-version", "1.0.0"),
            producer="producer",
            node_digest="sha256:" + "c" * 64,
        )
    nodes = _nodes()
    edges = tuple(
        LineageEdge(
            edge_id=f"edge-{index}",
            parent_node_id=f"node-{index}",
            child_node_id=f"node-{index + 1}",
            relation=LineageRelation.DERIVED_FROM,
        )
        for index in range(1, 7)
    )
    with pytest.raises(ValidationError, match="directed cycle"):
        LineageGraph(
            graph_id="graph-cycle",
            version="1.0.0",
            nodes=nodes,
            edges=(
                *edges,
                LineageEdge(
                    edge_id="edge-cycle",
                    parent_node_id="node-7",
                    child_node_id="node-1",
                    relation=LineageRelation.DERIVED_FROM,
                ),
            ),
            graph_digest="sha256:" + "d" * 64,
        )


def test_upstream_boundary_is_explicitly_caller_declared() -> None:
    assert M2602_UPSTREAM_MEDIA_TYPE == "application/vnd.glio-proteogen.m26-01+json"
