"""Focused schema and immutable-link tests for provisional M27-02."""

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m27_02 import (
    M2702_M2701_INPUT_MEDIA_TYPE,
    M2702_OUTPUT_MEDIA_TYPE,
    M2702_PROVISIONAL_ABI,
    LineageEdge,
    LineageGraph,
    LineageNode,
    LineageNodeKind,
    LineageRelation,
    LineageStatus,
    ReproducibilityBundle,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 8
_NODE_KIND_COUNT = 7
_VERSION = "1.0.0"
_DIGEST = "sha256:" + "a" * 64


def _artifact(identifier: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version=_VERSION,
        digest=_DIGEST,
        media_type="application/json",
    )


def _evidence(identifier: str = "evidence.m2702") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(identifier),
        role="evidence",
        claim="synthetic contract evidence",
    )


def _node(identifier: str, kind: LineageNodeKind) -> LineageNode:
    return LineageNode(
        node_id=identifier,
        kind=kind,
        name=identifier,
        version=_VERSION,
        digest=_DIGEST,
        media_type="application/json",
        evidence=(_evidence(),),
    )


def test_provisional_schemas_require_immutable_lineage_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "graph",
        "node",
        "edge",
        "bundle",
        "finding",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["immutableLineageRequired"] is True
        assert metadata["queryableGraphRequired"] is True
        assert metadata["exactVersionTraceabilityRequired"] is True
        assert metadata["reproducibilityBundleRequired"] is True
        assert metadata["brokenLinkRejectionRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "complex activity"
        assert metadata["upstreamInputMediaType"] == M2702_M2701_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2702_OUTPUT_MEDIA_TYPE
    assert M2702_PROVISIONAL_ABI is True


def test_lineage_kinds_and_resolution_states_are_explicit() -> None:
    assert len(tuple(LineageNodeKind)) == _NODE_KIND_COUNT
    assert LineageRelation.DERIVED_FROM.value == "derived_from"
    assert LineageStatus.ABSTAINED.value == "abstained"


def test_bundle_requires_root_and_unique_producing_versions() -> None:
    with pytest.raises(ValidationError, match="root must be included"):
        ReproducibilityBundle(
            bundle_id="bundle.invalid",
            version=_VERSION,
            root_node_id="node.missing",
            node_ids=("node.present",),
            producing_versions=(_VERSION,),
            manifest_digest=_DIGEST,
            evidence=(_evidence(),),
        )
    with pytest.raises(ValidationError, match="producing versions must be unique"):
        ReproducibilityBundle(
            bundle_id="bundle.duplicate-version",
            version=_VERSION,
            root_node_id="node.present",
            node_ids=("node.present",),
            producing_versions=(_VERSION, _VERSION),
            manifest_digest=_DIGEST,
            evidence=(_evidence(),),
        )


def test_graph_rejects_unknown_endpoints_and_cycles() -> None:
    first = _node("node.first", LineageNodeKind.SOURCE_DATA)
    second = _node("node.second", LineageNodeKind.TRANSFORMATION)
    bundle = ReproducibilityBundle(
        bundle_id="bundle.graph",
        version=_VERSION,
        root_node_id=first.node_id,
        node_ids=(first.node_id, second.node_id),
        edge_ids=("edge.one",),
        producing_versions=(_VERSION,),
        manifest_digest=_DIGEST,
        evidence=(_evidence(),),
    )
    edge = LineageEdge(
        edge_id="edge.one",
        source_node_id=first.node_id,
        target_node_id=second.node_id,
        relation=LineageRelation.DERIVED_FROM,
        producing_version=_VERSION,
        evidence=(_evidence(),),
    )
    graph = LineageGraph(
        graph_id="graph.valid",
        version=_VERSION,
        nodes=(first, second),
        edges=(edge,),
        reproducibility_bundle=bundle,
        evidence=(_evidence(),),
    )
    assert graph.edges == (edge,)
    with pytest.raises(ValidationError, match="unknown node"):
        LineageGraph.model_validate(
            graph.model_copy(
                update={"edges": (edge.model_copy(update={"target_node_id": "node.missing"}),)}
            ),
            strict=True,
        )
    reverse = edge.model_copy(
        update={
            "edge_id": "edge.reverse",
            "source_node_id": second.node_id,
            "target_node_id": first.node_id,
        }
    )
    with pytest.raises(ValidationError, match="directed cycle"):
        LineageGraph.model_validate(
            graph.model_copy(
                update={
                    "edges": (edge, reverse),
                    "reproducibility_bundle": bundle.model_copy(
                        update={"edge_ids": (edge.edge_id, reverse.edge_id)}
                    ),
                }
            ),
            strict=True,
        )
