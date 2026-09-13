"""Adversarial contract boundaries for GLIO-ECGI research requests."""

from __future__ import annotations

from math import inf

import pytest
from pydantic import ValidationError

from glio_proteogen.research.proteogenomic_state import (
    EdgeKind,
    EvidenceModality,
    EvidenceObservation,
    EvidenceState,
    ExternalKinaseEstimate,
    ExternalKinaseProfile,
    GraphEdge,
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    PublicTopologySource,
    TopologyProvenance,
    graph_topology_digest,
)
from glio_proteogen.research.proteogenomic_state.canonical import sha256_digest

SOURCE_DIGEST = sha256_digest("contract-test")


def _node(node_id: str, kind: NodeKind = NodeKind.PROTEIN) -> GraphNode:
    return GraphNode(node_id=node_id, kind=kind)


def _topology_source(*scope_node_ids: str) -> PublicTopologySource:
    return PublicTopologySource(
        source_id="public.example.release1",
        resource_name="Example public resource",
        resource_release="1",
        record_id="record.example",
        record_title="Example topology record",
        source_uri="https://example.org/record.example.json",
        source_format="application/json",
        source_digest=SOURCE_DIGEST,
        source_size_bytes=128,
        license_id="CC0-1.0",
        license_uri="https://creativecommons.org/publicdomain/zero/1.0/",
        retrieved_on="2026-08-27",
        scope_node_ids=scope_node_ids,
    )


def test_observation_state_contract_is_closed() -> None:
    with pytest.raises(ValidationError, match="require effect and error"):
        EvidenceObservation(
            observation_id="obs.bad",
            node_id="protein.a",
            modality=EvidenceModality.PROTEOMICS,
            state=EvidenceState.OBSERVED,
            quality_weight=1.0,
            provenance_digest=SOURCE_DIGEST,
        )
    with pytest.raises(ValidationError, match="cannot carry numeric"):
        EvidenceObservation(
            observation_id="obs.missing",
            node_id="protein.a",
            modality=EvidenceModality.PROTEOMICS,
            state=EvidenceState.MISSING,
            standardized_effect=-1.0,
            standard_error=0.2,
            quality_weight=0.0,
            provenance_digest=SOURCE_DIGEST,
        )
    with pytest.raises(ValidationError, match="finite number"):
        EvidenceObservation(
            observation_id="obs.infinite",
            node_id="protein.a",
            modality=EvidenceModality.PROTEOMICS,
            state=EvidenceState.OBSERVED,
            standardized_effect=inf,
            standard_error=0.2,
            quality_weight=1.0,
            provenance_digest=SOURCE_DIGEST,
        )


@pytest.mark.parametrize(
    ("edge", "message"),
    [
        (
            GraphEdge(
                edge_id="edge.member",
                source_id="protein.a",
                target_id="protein.b",
                kind=EdgeKind.MEMBER_OF,
                sign=1,
                weight=1.0,
            ),
            "member_of",
        ),
        (
            GraphEdge(
                edge_id="edge.kinase",
                source_id="protein.a",
                target_id="protein.b",
                kind=EdgeKind.KINASE_SUBSTRATE,
                sign=1,
                weight=1.0,
            ),
            "kinase_substrate",
        ),
        (
            GraphEdge(
                edge_id="edge.pathway",
                source_id="protein.a",
                target_id="protein.b",
                kind=EdgeKind.PARTICIPATES_IN,
                sign=1,
                weight=1.0,
            ),
            "pathway",
        ),
    ],
)
def test_graph_rejects_incompatible_edge_types(edge: GraphEdge, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ProteogenomicStateRequest(
            sample_id="sample.invalid.edge",
            nodes=(_node("protein.a"), _node("protein.b")),
            edges=(edge,),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


def test_graph_rejects_duplicates_unresolved_references_and_self_edges() -> None:
    with pytest.raises(ValidationError, match="node identifiers must be unique"):
        ProteogenomicStateRequest(
            sample_id="sample.duplicate",
            nodes=(_node("protein.a"), _node("protein.a")),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    with pytest.raises(ValidationError, match="unresolved"):
        ProteogenomicStateRequest(
            sample_id="sample.unresolved",
            nodes=(_node("protein.a"),),
            edges=(
                GraphEdge(
                    edge_id="edge.unresolved",
                    source_id="protein.a",
                    target_id="protein.absent",
                    kind=EdgeKind.REGULATES,
                    sign=1,
                    weight=1.0,
                ),
            ),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    with pytest.raises(ValidationError, match="self edges"):
        ProteogenomicStateRequest(
            sample_id="sample.self",
            nodes=(_node("protein.a"),),
            edges=(
                GraphEdge(
                    edge_id="edge.self",
                    source_id="protein.a",
                    target_id="protein.a",
                    kind=EdgeKind.REGULATES,
                    sign=1,
                    weight=1.0,
                ),
            ),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


@pytest.mark.parametrize("ordering", ["forward", "reversed"])
def test_graph_rejects_parallel_semantic_relations_independent_of_edge_order(
    ordering: str,
) -> None:
    edges = (
        GraphEdge(
            edge_id="edge.substrate.positive",
            source_id="kinase.k",
            target_id="phosphosite.s",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=1,
            weight=1.0,
        ),
        GraphEdge(
            edge_id="edge.substrate.negative",
            source_id="kinase.k",
            target_id="phosphosite.s",
            kind=EdgeKind.KINASE_SUBSTRATE,
            sign=-1,
            weight=0.5,
        ),
    )
    with pytest.raises(ValidationError, match="parallel semantic relations"):
        ProteogenomicStateRequest(
            sample_id="sample.parallel.relation",
            nodes=(
                GraphNode(node_id="kinase.k", kind=NodeKind.KINASE),
                GraphNode(node_id="phosphosite.s", kind=NodeKind.PHOSPHOSITE),
            ),
            edges=tuple(reversed(edges)) if ordering == "reversed" else edges,
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


def test_structural_limits_and_strict_unknown_fields_are_enforced() -> None:
    with pytest.raises(ValidationError, match="at most 256"):
        ProteogenomicStateRequest(
            sample_id="sample.too.large",
            nodes=tuple(_node(f"protein.n{index}") for index in range(257)),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        GraphNode.model_validate(
            {"node_id": "protein.a", "kind": NodeKind.PROTEIN, "unexpected": True}
        )


def test_external_kinase_profile_requires_exact_kinase_node_identifiers() -> None:
    external = ExternalKinaseProfile(
        profile_id="kinophos.test",
        source_digest=SOURCE_DIGEST,
        estimates=(
            ExternalKinaseEstimate(
                kinase_id="protein.a",
                activity=0.0,
                lower_bound=-0.5,
                upper_bound=0.5,
            ),
        ),
    )
    with pytest.raises(ValidationError, match="exact kinase"):
        ProteogenomicStateRequest(
            sample_id="sample.external",
            nodes=(_node("protein.a"),),
            external_kinase_profile=external,
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


def test_topology_provenance_is_content_addressed_unique_and_graph_closed() -> None:
    node = _node("protein.a")
    digest = graph_topology_digest({"nodes": [node], "edges": []})
    source = _topology_source("protein.a")
    topology = TopologyProvenance(
        topology_digest=digest,
        derivation="caller_curated",
        sources=(source,),
        curation_note="Public context; caller remains responsible for edge interpretation.",
    )
    request = ProteogenomicStateRequest(
        sample_id="sample.topology",
        nodes=(node,),
        topology_provenance=topology,
        bootstrap_replicates=8,
        permutation_replicates=32,
    )
    assert request.topology_provenance == topology

    with pytest.raises(ValidationError, match="source identifiers must be unique"):
        TopologyProvenance(
            topology_digest=digest,
            derivation="caller_curated",
            sources=(source, source),
            curation_note="Duplicate source declarations are ambiguous.",
        )
    with pytest.raises(ValidationError, match="digest does not match"):
        ProteogenomicStateRequest(
            sample_id="sample.topology.digest",
            nodes=(node,),
            topology_provenance=topology.model_copy(
                update={"topology_digest": sha256_digest("wrong topology")}
            ),
            bootstrap_replicates=8,
            permutation_replicates=32,
        )
    unresolved = topology.model_copy(update={"sources": (_topology_source("protein.absent"),)})
    with pytest.raises(ValidationError, match="scope references an unresolved node"):
        ProteogenomicStateRequest(
            sample_id="sample.topology.scope",
            nodes=(node,),
            topology_provenance=unresolved,
            bootstrap_replicates=8,
            permutation_replicates=32,
        )


def test_topology_source_requires_public_https_locations() -> None:
    document = _topology_source("protein.a").model_dump(mode="json")
    document["source_uri"] = "http://example.org/record.example.json"
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        PublicTopologySource.model_validate(document)
    with pytest.raises(ValidationError, match="scope node identifiers must be unique"):
        _topology_source("protein.a", "protein.a")


def test_edge_specific_properties_are_validated_before_graph_construction() -> None:
    with pytest.raises(ValidationError, match="essential"):
        GraphEdge(
            edge_id="edge.bad.essential",
            source_id="protein.a",
            target_id="protein.b",
            kind=EdgeKind.REGULATES,
            sign=1,
            weight=1.0,
            essential=True,
        )
    with pytest.raises(ValidationError, match="positive sign"):
        GraphEdge(
            edge_id="edge.bad.sign",
            source_id="protein.a",
            target_id="complex.a",
            kind=EdgeKind.MEMBER_OF,
            sign=-1,
            weight=1.0,
        )
