"""Locked annotation topology for the two independent KNCC GBM result blocks."""

from __future__ import annotations

from functools import lru_cache

from glio_proteogen.research.longitudinal_gbm_kinase_transition.catalog import (
    load_kinase_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    PROFILE_ID as KINASE_PROFILE_ID,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.catalog import (
    EXPECTED_PATHWAYS,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    PROFILE_ID as REACTOME_PROFILE_ID,
)

from .canonical import topology_payload_digest
from .contracts import (
    TOPOLOGY_ID,
    FactorGraphBlock,
    FactorGraphContainmentEdge,
    FactorGraphNode,
    FactorGraphNodeKind,
    FactorGraphTopology,
)

PROTEIN_BLOCK_NODE_ID = "block.protein_reactome"
PHOSPHOSITE_BLOCK_NODE_ID = "block.phosphosite_sphinks"
GLOBAL_RECURRENCE_NODE_ID = "reactome.global_recurrence"
SUBTYPE_ORDER = ("GPM", "MTC", "NEU", "PPR")


def _block_nodes() -> tuple[FactorGraphNode, FactorGraphNode]:
    return (
        FactorGraphNode(
            node_id=PROTEIN_BLOCK_NODE_ID,
            block=FactorGraphBlock.PROTEIN_REACTOME,
            kind=FactorGraphNodeKind.COMPUTATION_BLOCK,
            biological_identifier="PDC000514.ReactomeV97",
            label="KNCC protein / fitted Reactome concordance block",
            child_profile_id=REACTOME_PROFILE_ID,
            learned_semantics="child_result_container_only",
        ),
        FactorGraphNode(
            node_id=PHOSPHOSITE_BLOCK_NODE_ID,
            block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
            kind=FactorGraphNodeKind.COMPUTATION_BLOCK,
            biological_identifier="PDC000515.SPHINKS",
            label="KNCC phosphosite / fitted SPHINKS concordance block",
            child_profile_id=KINASE_PROFILE_ID,
            learned_semantics="child_result_container_only",
        ),
    )


def _reactome_nodes() -> tuple[FactorGraphNode, ...]:
    global_node = FactorGraphNode(
        node_id=GLOBAL_RECURRENCE_NODE_ID,
        block=FactorGraphBlock.PROTEIN_REACTOME,
        kind=FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR,
        biological_identifier="global_recurrence",
        label="Fitted global recurrence concordance coordinate",
        child_profile_id=REACTOME_PROFILE_ID,
        learned_semantics="child_source_cohort_fitted_coordinate",
    )
    pathway_nodes = tuple(
        FactorGraphNode(
            node_id=f"reactome.pathway.{index:02d}",
            block=FactorGraphBlock.PROTEIN_REACTOME,
            kind=FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR,
            biological_identifier=reactome_id,
            label=f"{domain_id}: {pathway_name}",
            child_profile_id=REACTOME_PROFILE_ID,
            learned_semantics="child_source_cohort_fitted_coordinate",
        )
        for index, (domain_id, reactome_id, pathway_name) in enumerate(EXPECTED_PATHWAYS)
    )
    return (global_node, *pathway_nodes)


def _kinase_nodes() -> tuple[FactorGraphNode, ...]:
    catalog = load_kinase_transition_catalog()
    kinase_nodes = tuple(
        FactorGraphNode(
            node_id=f"sphinks.kinase.{hypothesis.kinase}",
            block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
            kind=FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR,
            biological_identifier=hypothesis.kinase,
            label=f"{hypothesis.kinase} fitted {hypothesis.subtype} signature coordinate",
            child_profile_id=KINASE_PROFILE_ID,
            learned_semantics="child_source_cohort_fitted_coordinate",
        )
        for hypothesis in catalog.hypotheses
    )
    subtype_nodes = tuple(
        FactorGraphNode(
            node_id=f"sphinks.subtype.{subtype}",
            block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
            kind=FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR,
            biological_identifier=subtype,
            label=f"{subtype} fitted equal-kinase subtype signature coordinate",
            child_profile_id=KINASE_PROFILE_ID,
            learned_semantics="child_source_cohort_fitted_coordinate",
        )
        for subtype in SUBTYPE_ORDER
    )
    return (*kinase_nodes, *subtype_nodes)


def _containment_edges(
    nodes: tuple[FactorGraphNode, ...],
) -> tuple[FactorGraphContainmentEdge, ...]:
    edges: list[FactorGraphContainmentEdge] = []
    for index, node in enumerate(nodes):
        if node.kind is FactorGraphNodeKind.COMPUTATION_BLOCK:
            continue
        source = (
            PROTEIN_BLOCK_NODE_ID
            if node.block is FactorGraphBlock.PROTEIN_REACTOME
            else PHOSPHOSITE_BLOCK_NODE_ID
        )
        edges.append(
            FactorGraphContainmentEdge(
                edge_id=f"containment.edge.{index:02d}",
                source_node_id=source,
                target_node_id=node.node_id,
            )
        )
    return tuple(edges)


@lru_cache(maxsize=1)
def factor_graph_topology() -> FactorGraphTopology:
    """Return the content-bound topology after the fitted kinase catalog validates."""

    nodes = (*_block_nodes(), *_reactome_nodes(), *_kinase_nodes())
    edges = _containment_edges(nodes)
    payload = {
        "topology_id": TOPOLOGY_ID,
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "containment_edges": [edge.model_dump(mode="json") for edge in edges],
        "cross_block_edges": [],
        "numerical_cross_block_edge_count": 0,
        "containment_edge_role": "annotation_only",
    }
    return FactorGraphTopology(
        nodes=nodes,
        containment_edges=edges,
        topology_digest=topology_payload_digest(payload),
    )


__all__ = [
    "GLOBAL_RECURRENCE_NODE_ID",
    "PHOSPHOSITE_BLOCK_NODE_ID",
    "PROTEIN_BLOCK_NODE_ID",
    "SUBTYPE_ORDER",
    "factor_graph_topology",
]
