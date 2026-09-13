from __future__ import annotations

from typing import cast

import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
    complex_transition_source_catalog,
)
from tools import build_cptac_gbm_evidence_graph_projection as projection


def _receipts() -> tuple[dict[str, object], dict[str, object]]:
    source = complex_transition_source_catalog()
    manifest = "sha256:" + "1" * 64
    complex_factors = [
        {
                "complex_id": binding.reactome_id,
                "state": "observed",
                "phosphosite": {
                    "features": [
                        {
                            "feature_id": f"{binding.reactome_id}.S1",
                            "gene": binding.member_bindings[0].gene_symbol,
                            "paired_support": 20,
                            "loading": 0.5,
                            "parent_trace_digest": "sha256:" + "2" * 64,
                        }
                    ]
                },
        }
        for binding in source.complexes
    ]
    pathway_ids = sorted(
        {binding.anchor_pathway.top_level_pathway_id for binding in source.complexes}
    )
    pathways = [{"pathway_id": pathway_id, "state": "observed"} for pathway_id in pathway_ids]
    return (
        {
            "source_manifest_digest": manifest,
            "source_complex_catalog_digest": source.content_digest,
            "factors": complex_factors,
        },
        {
            "source_manifest_digest": manifest,
            "source_complex_catalog_digest": source.content_digest,
            "pathways": pathways,
        },
    )


def test_projection_is_bounded_and_separates_annotation_site_links() -> None:
    complex_receipt, pathway_receipt = _receipts()
    result = projection._build_projection(
        complex_receipt, pathway_receipt, complex_transition_source_catalog().complexes
    )
    topology = cast("dict[str, object]", result["topology"])
    nodes = cast("list[dict[str, object]]", topology["nodes"])
    edges = cast("list[dict[str, object]]", topology["edges"])
    assert len(nodes) <= projection.MAX_NODES
    assert len(edges) <= projection.MAX_EDGES
    edge_family_counts = cast("dict[str, int]", result["edge_family_counts"])
    assert edge_family_counts["protein_to_complex"] > 0
    assert edge_family_counts["complex_to_pathway"] == 28
    sites = cast("list[dict[str, object]]", result["phosphosite_projection"])
    assert sites[0]["annotation_only_parent_link"] is True
    assert sites[0]["numerical_site_edges"] is False
    semantics = cast("dict[str, object]", result["semantics"])
    assert semantics["unsupported_relations"] == ["kinase_substrate"]


def test_projection_rejects_mismatched_source_receipts() -> None:
    complex_receipt, pathway_receipt = _receipts()
    pathway_receipt["source_manifest_digest"] = "sha256:" + "3" * 64
    with pytest.raises(ValueError, match="manifest digest"):
        projection._build_projection(
            complex_receipt, pathway_receipt, complex_transition_source_catalog().complexes
        )


def test_projection_rejects_duplicate_complex_factor_ids() -> None:
    complex_receipt, pathway_receipt = _receipts()
    factors = cast("list[dict[str, object]]", complex_receipt["factors"])
    factors.append(dict(factors[0]))
    with pytest.raises(ValueError, match="duplicate"):
        projection._build_projection(
            complex_receipt, pathway_receipt, complex_transition_source_catalog().complexes
        )
