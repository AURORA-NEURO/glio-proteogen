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


def test_projection_attaches_source_factor_bootstrap_intervals() -> None:
    complex_receipt, pathway_receipt = _receipts()
    complex_digest = "sha256:" + "a" * 64
    pathway_digest = "sha256:" + "b" * 64
    bootstrap_receipt = {
        "schema_version": projection.BOOTSTRAP_MODEL_ID,
        "source_manifest_digest": complex_receipt["source_manifest_digest"],
        "source_complex_catalog_digest": complex_receipt["source_complex_catalog_digest"],
        "factor_receipts": {"complex": complex_digest, "pathway": pathway_digest},
        "replicates_requested": 64,
        "complexes": [
            {
                "complex_id": factor["complex_id"],
                "protein_loading_cosine": {
                    "support": 64,
                    "lower": 0.8,
                    "median": 0.9,
                    "upper": 1.0,
                },
                "phosphosite_loading_cosine": {
                    "support": 64,
                    "lower": 0.7,
                    "median": 0.85,
                    "upper": 0.98,
                },
            }
            for factor in cast("list[dict[str, object]]", complex_receipt["factors"])
        ],
        "pathways": [
            {
                "pathway_id": pathway["pathway_id"],
                "protein_loading_cosine": {
                    "support": 64,
                    "lower": 0.8,
                    "median": 0.9,
                    "upper": 1.0,
                },
                "phosphosite_loading_cosine": {
                    "support": 64,
                    "lower": 0.7,
                    "median": 0.85,
                    "upper": 0.98,
                },
            }
            for pathway in cast("list[dict[str, object]]", pathway_receipt["pathways"])
        ],
    }
    result = projection._build_projection(
        complex_receipt,
        pathway_receipt,
        complex_transition_source_catalog().complexes,
        complex_receipt_digest=complex_digest,
        pathway_receipt_digest=pathway_digest,
        bootstrap_receipt=bootstrap_receipt,
        bootstrap_receipt_digest="sha256:" + "c" * 64,
    )
    topology = cast("dict[str, object]", result["topology"])
    nodes = cast("list[dict[str, object]]", topology["nodes"])
    complex_node = next(node for node in nodes if node["kind"] == "complex")
    assert cast("dict[str, object]", complex_node["bootstrap_uncertainty"])[
        "protein_loading_cosine"
    ] == {"support": 64, "lower": 0.8, "median": 0.9, "upper": 1.0}
    summary = cast("dict[str, object]", result["bootstrap_uncertainty"])
    assert summary["replicates_requested"] == 64


def test_projection_rejects_bootstrap_factor_digest_mismatch() -> None:
    complex_receipt, pathway_receipt = _receipts()
    bootstrap_receipt = {
        "schema_version": projection.BOOTSTRAP_MODEL_ID,
        "source_manifest_digest": complex_receipt["source_manifest_digest"],
        "source_complex_catalog_digest": complex_receipt["source_complex_catalog_digest"],
        "factor_receipts": {"complex": "sha256:" + "x" * 64, "pathway": "sha256:" + "b" * 64},
        "complexes": [],
        "pathways": [],
    }
    with pytest.raises(ValueError, match="complex factor digest"):
        projection._build_projection(
            complex_receipt,
            pathway_receipt,
            complex_transition_source_catalog().complexes,
            complex_receipt_digest="sha256:" + "a" * 64,
            pathway_receipt_digest="sha256:" + "b" * 64,
            bootstrap_receipt=bootstrap_receipt,
        )


def test_projection_opt_in_kinase_crosswalk_adds_real_experimental_edges() -> None:
    complex_receipt, pathway_receipt = _receipts()
    complex_digest = "sha256:" + "a" * 64
    pathway_digest = "sha256:" + "b" * 64
    factors = cast("list[dict[str, object]]", complex_receipt["factors"])
    phosphosite = cast("dict[str, object]", factors[0]["phosphosite"])
    features = cast("list[dict[str, object]]", phosphosite["features"])
    feature_id = features[0]["feature_id"]
    kinase_map = {
        "schema_version": projection.KINASE_MAP_MODEL_ID,
        "source_manifest_digest": complex_receipt["source_manifest_digest"],
        "factor_receipt_digest": complex_digest,
        "algorithm_profile": {"model_id": projection.KINASE_MAP_MODEL_ID},
        "algorithm_profile_digest": "",
        "receipt_digest": "",
        "source_kinase_catalog": {"content_digest": "sha256:" + "d" * 64},
        "edges": [
            {
                "kinase_id": "CDK1",
                "feature_id": feature_id,
                "edge_weight": 0.42,
                "sign": 1,
                "source_edge_ids": ["table5d:1"],
                "source_site_labels": ["GENE-S1s"],
                "known_substrate_fraction": 1.0,
                "mean_svm_probability": 0.8,
                "mean_spearman_rho": 0.525,
            }
        ],
    }
    profile = cast("dict[str, object]", kinase_map["algorithm_profile"])
    kinase_map["algorithm_profile_digest"] = "sha256:" + projection.hashlib.sha256(
        projection._canonical_bytes(profile)
    ).hexdigest()
    digest_payload = {key: value for key, value in kinase_map.items() if key != "receipt_digest"}
    kinase_map["receipt_digest"] = "sha256:" + projection.hashlib.sha256(
        projection._canonical_bytes(digest_payload)
    ).hexdigest()
    result = projection._build_projection(
        complex_receipt,
        pathway_receipt,
        complex_transition_source_catalog().complexes,
        complex_receipt_digest=complex_digest,
        pathway_receipt_digest=pathway_digest,
        kinase_edge_map=kinase_map,
        kinase_edge_map_digest="sha256:" + "e" * 64,
    )
    topology = cast("dict[str, object]", result["topology"])
    edges = cast("list[dict[str, object]]", topology["edges"])
    kinase_edges = [edge for edge in edges if edge["kind"] == "kinase_substrate"]
    assert len(kinase_edges) == 1
    assert kinase_edges[0]["weight"] == 0.42
    assert cast("dict[str, int]", result["edge_family_counts"])["kinase_substrate"] == 1
    semantics = cast("dict[str, object]", result["semantics"])
    assert "kinase_substrate" in cast("list[str]", semantics["numerical_edge_families"])
    assert semantics["unsupported_relations"] == []


def test_projection_rejects_forged_kinase_map_digest() -> None:
    complex_receipt, pathway_receipt = _receipts()
    kinase_map = {
        "schema_version": projection.KINASE_MAP_MODEL_ID,
        "source_manifest_digest": complex_receipt["source_manifest_digest"],
        "factor_receipt_digest": "sha256:" + "a" * 64,
        "algorithm_profile": {"model_id": projection.KINASE_MAP_MODEL_ID},
        "algorithm_profile_digest": "sha256:" + "0" * 64,
        "receipt_digest": "sha256:" + "1" * 64,
        "edges": [],
    }
    with pytest.raises(ValueError, match="algorithm profile digest"):
        projection._build_projection(
            complex_receipt,
            pathway_receipt,
            complex_transition_source_catalog().complexes,
            complex_receipt_digest="sha256:" + "a" * 64,
            kinase_edge_map=kinase_map,
        )
