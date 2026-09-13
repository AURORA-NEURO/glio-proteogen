# ruff: noqa: C901, E501, PLR0912, T201, TRY003, TRY004
"""Build a bounded, source-bound evidence-graph projection for matched GBM.

The projection joins exact Reactome complex memberships to the fitted protein
and protein-adjusted phosphosite receipts.  Protein-to-complex and
complex-to-pathway edges are the only numerical families.  Phosphosite-to-
parent links are retained as annotation metadata, never converted into a
numerical edge; no kinase-substrate source is present in the matched capture.
The output is a topology/provenance receipt and contains no patient values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Final, cast

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
    ReactomeComplexBinding,
    complex_transition_source_catalog,
)
from tools.capture_cptac_gbm_matched_source_manifest import _canonical_bytes

MODEL_ID: Final = "cptac-gbm-evidence-graph-projection/1.0.0"
MAX_NODES: Final = 256
MAX_EDGES: Final = 2_048
PROTEIN_EDGE_WEIGHT: Final = 0.90
PATHWAY_EDGE_WEIGHT: Final = 0.80
HUBER_DELTA: Final = 1.345
ROBUST_SCALE_FLOOR: Final = 0.05
OBJECTIVE_TOLERANCE: Final = 1.0e-10
MIN_COSINE_SUPPORT: Final = 2
NORM_EPSILON: Final = 1.0e-12


def _digest_bytes(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _node_id(kind: str, identifier: str) -> str:
    return f"{kind}.{identifier}"


def _edge_id(source: str, target: str, kind: str) -> str:
    return f"edge.{kind}.{source}.{target}"


def _receipt(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"factor receipt is not a JSON object: {path.name}")
    return cast("dict[str, object]", value)


def _validate_receipt_pair(
    complex_receipt: dict[str, object], pathway_receipt: dict[str, object]
) -> tuple[str, str]:
    complex_manifest = complex_receipt.get("source_manifest_digest")
    pathway_manifest = pathway_receipt.get("source_manifest_digest")
    complex_catalog = complex_receipt.get("source_complex_catalog_digest")
    pathway_catalog = pathway_receipt.get("source_complex_catalog_digest")
    if not isinstance(complex_manifest, str) or complex_manifest != pathway_manifest:
        raise ValueError("complex and pathway receipts do not share the exact source manifest digest")
    if not isinstance(complex_catalog, str) or complex_catalog != pathway_catalog:
        raise ValueError("complex and pathway receipts do not share the exact source catalog digest")
    factors = complex_receipt.get("factors")
    pathways = pathway_receipt.get("pathways")
    if not isinstance(factors, list) or not isinstance(pathways, list):
        raise ValueError("factor receipts are missing factors or pathways")
    return complex_manifest, complex_catalog


def _factor_by_complex(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    factors = cast("list[object]", receipt["factors"])
    result: dict[str, dict[str, object]] = {}
    for item in factors:
        if not isinstance(item, dict):
            raise ValueError("complex factor receipt contains a non-object factor")
        factor = cast("dict[str, object]", item)
        complex_id = factor.get("complex_id")
        if not isinstance(complex_id, str) or complex_id in result:
            raise ValueError("complex factor receipt has duplicate or invalid complex IDs")
        result[complex_id] = factor
    return result


def _pathway_by_id(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    pathways = cast("list[object]", receipt["pathways"])
    result: dict[str, dict[str, object]] = {}
    for item in pathways:
        if not isinstance(item, dict):
            raise ValueError("pathway factor receipt contains a non-object pathway")
        pathway = cast("dict[str, object]", item)
        pathway_id = pathway.get("pathway_id")
        if not isinstance(pathway_id, str) or pathway_id in result:
            raise ValueError("pathway factor receipt has duplicate or invalid pathway IDs")
        result[pathway_id] = pathway
    return result


def _site_projection(
    bindings: tuple[ReactomeComplexBinding, ...],
    complex_factors: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    by_site: dict[str, dict[str, object]] = {}
    binding_by_id = {binding.reactome_id: binding for binding in bindings}
    for complex_id, factor in complex_factors.items():
        phosphosite = factor.get("phosphosite")
        if not isinstance(phosphosite, dict):
            continue
        features = phosphosite.get("features")
        if not isinstance(features, list):
            raise ValueError(f"complex factor has malformed phosphosite features: {complex_id}")
        binding = binding_by_id.get(complex_id)
        if binding is None:
            raise ValueError(f"factor references a complex absent from the source catalog: {complex_id}")
        pathway_ids = [binding.anchor_pathway.top_level_pathway_id]
        for item in features:
            if not isinstance(item, dict):
                raise ValueError("phosphosite feature projection contains a non-object")
            feature = cast("dict[str, object]", item)
            feature_id = feature.get("feature_id")
            gene = feature.get("gene")
            if not isinstance(feature_id, str) or not isinstance(gene, str):
                raise ValueError("phosphosite feature projection lacks feature_id or gene")
            entry = by_site.setdefault(
                feature_id,
                {
                    "feature_id": feature_id,
                    "parent_protein": gene,
                    "complex_ids": [],
                    "pathway_ids": [],
                    "annotation_only_parent_link": True,
                    "numerical_site_edges": False,
                },
            )
            complex_ids = cast("list[str]", entry["complex_ids"])
            pathway_id_list = cast("list[str]", entry["pathway_ids"])
            if complex_id not in complex_ids:
                complex_ids.append(complex_id)
            for pathway_id in pathway_ids:
                if pathway_id not in pathway_id_list:
                    pathway_id_list.append(pathway_id)
            for field in ("paired_support", "parent_alpha", "parent_beta", "residual_scale", "loading"):
                if field in feature:
                    entry[field] = feature[field]
            entry["parent_trace_digest"] = feature.get("parent_trace_digest")
    for entry in by_site.values():
        entry["complex_ids"] = sorted(cast("list[str]", entry["complex_ids"]))
        entry["pathway_ids"] = sorted(cast("list[str]", entry["pathway_ids"]))
    return [by_site[key] for key in sorted(by_site)]


def _robust_summary(values: list[float]) -> dict[str, object]:
    """Summarize concordance scores without allowing one factor to dominate."""

    if not values:
        return {"support": 0, "center": None, "scale": None}
    array = np.asarray(values, dtype=np.float64)
    center = float(np.median(array))
    scale = max(float(np.median(np.abs(array - center)) * 1.4826), ROBUST_SCALE_FLOOR)
    for _ in range(32):
        residual = (array - center) / scale
        weights = np.minimum(1.0, HUBER_DELTA / np.maximum(np.abs(residual), 1.0e-15))
        updated = float(np.sum(weights * array) / np.sum(weights))
        if abs(updated - center) <= OBJECTIVE_TOLERANCE:
            center = updated
            break
        center = updated
    return {
        "support": len(values),
        "center": round(center, 8),
        "scale": round(max(float(np.median(np.abs(array - center)) * 1.4826), ROBUST_SCALE_FLOOR), 8),
    }


def _loading_map(factor: object) -> dict[str, float]:
    if not isinstance(factor, dict):
        return {}
    members = factor.get("protein_members")
    protein_factor = factor.get("protein_factor")
    if not isinstance(members, list) or not isinstance(protein_factor, dict):
        return {}
    loadings = protein_factor.get("loadings")
    if not isinstance(loadings, list) or len(loadings) != len(members):
        return {}
    return {
        member: float(loading)
        for member, loading in zip(members, loadings, strict=True)
        if isinstance(member, str) and isinstance(loading, (int, float))
    }


def _cosine(left: list[float], right: list[float]) -> float | None:
    if len(left) < MIN_COSINE_SUPPORT or len(left) != len(right):
        return None
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
    if denominator <= NORM_EPSILON:
        return None
    return float(np.dot(left_array, right_array) / denominator)


def _edge_family_diagnostics(
    bindings: tuple[ReactomeComplexBinding, ...],
    complex_factors: dict[str, dict[str, object]],
    pathway_factors: dict[str, dict[str, object]],
) -> dict[str, object]:
    complex_pathway_scores: list[float] = []
    site_parent_scores: list[float] = []
    member_mass_scores: list[float] = []
    for binding in bindings:
        factor = complex_factors.get(binding.reactome_id)
        if factor is None or factor.get("state") != "observed":
            continue
        complex_loadings = _loading_map(factor)
        if complex_loadings:
            member_mass_scores.append(
                float(np.sum(np.abs(np.asarray(list(complex_loadings.values()), dtype=np.float64))))
                / max(np.sqrt(len(complex_loadings)), 1.0)
            )
        pathway = pathway_factors.get(binding.anchor_pathway.top_level_pathway_id)
        pathway_loadings = _loading_map(pathway)
        shared = sorted(set(complex_loadings) & set(pathway_loadings))
        score = _cosine(
            [complex_loadings[gene] for gene in shared],
            [pathway_loadings[gene] for gene in shared],
        )
        if score is not None:
            complex_pathway_scores.append(score)
        phosphosite = factor.get("phosphosite")
        features = phosphosite.get("features") if isinstance(phosphosite, dict) else None
        if not isinstance(features, list):
            continue
        site_values: list[float] = []
        parent_values: list[float] = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            gene = feature.get("gene")
            loading = feature.get("loading")
            if isinstance(gene, str) and isinstance(loading, (int, float)) and gene in complex_loadings:
                site_values.append(float(loading))
                parent_values.append(complex_loadings[gene])
        site_score = _cosine(site_values, parent_values)
        if site_score is not None:
            site_parent_scores.append(site_score)
    return {
        "protein_to_complex": {
            "diagnostic": "robust member-loading mass",
            **_robust_summary(member_mass_scores),
        },
        "complex_to_pathway": {
            "diagnostic": "robust cosine of shared protein loadings",
            **_robust_summary(complex_pathway_scores),
        },
        "phosphosite_to_parent": {
            "diagnostic": "robust cosine of site and parent loadings",
            **_robust_summary(site_parent_scores),
        },
        "applied_multipliers": {
            "protein_to_complex": 1.0,
            "complex_to_pathway": 1.0,
        },
        "selection_status": "diagnostic_only_not_nested_evaluation",
        "selection_grid": [0.0, 0.25, 0.5, 1.0, 2.0],
        "interpretation": (
            "Concordance diagnostics are source-cohort summaries. They do not tune edge weights, "
            "establish direction, or replace nested case-group evaluation."
        ),
    }


def _build_projection(
    complex_receipt: dict[str, object],
    pathway_receipt: dict[str, object],
    bindings: tuple[ReactomeComplexBinding, ...],
    *,
    complex_receipt_digest: str = "sha256:" + "0" * 64,
    pathway_receipt_digest: str = "sha256:" + "0" * 64,
) -> dict[str, object]:
    source_manifest, source_catalog = _validate_receipt_pair(complex_receipt, pathway_receipt)
    complex_factors = _factor_by_complex(complex_receipt)
    pathway_factors = _pathway_by_id(pathway_receipt)
    source_by_id = {binding.reactome_id: binding for binding in bindings}
    if set(complex_factors) - set(source_by_id):
        raise ValueError("complex receipt contains a complex outside the source catalog")
    nodes: dict[str, dict[str, object]] = {}
    edges: dict[str, dict[str, object]] = {}
    for binding in bindings:
        complex_node = _node_id("complex", binding.reactome_id)
        nodes.setdefault(
            complex_node,
            {"node_id": complex_node, "kind": "complex", "display_name": binding.name},
        )
        pathway_node = _node_id("pathway", binding.anchor_pathway.top_level_pathway_id)
        nodes.setdefault(
            pathway_node,
            {
                "node_id": pathway_node,
                "kind": "pathway",
                "display_name": binding.anchor_pathway.top_level_pathway_name,
            },
        )
        pathway_edge_id = _edge_id(complex_node, pathway_node, "participates_in")
        edges.setdefault(
            pathway_edge_id,
            {
                "edge_id": pathway_edge_id,
                "source_id": complex_node,
                "target_id": pathway_node,
                "kind": "participates_in",
                "sign": 1,
                "weight": PATHWAY_EDGE_WEIGHT,
                "essential": False,
                "edge_family": "complex_to_pathway",
                "source_semantics": "exact_direct_reactome_binding",
            },
        )
        for member in binding.member_bindings:
            protein_node = _node_id("protein", member.gene_symbol)
            nodes.setdefault(
                protein_node,
                {
                    "node_id": protein_node,
                    "kind": "protein",
                    "display_name": member.gene_symbol,
                },
            )
            member_edge_id = _edge_id(protein_node, complex_node, "member_of")
            edges.setdefault(
                member_edge_id,
                {
                    "edge_id": member_edge_id,
                    "source_id": protein_node,
                    "target_id": complex_node,
                    "kind": "member_of",
                    "sign": 1,
                    "weight": PROTEIN_EDGE_WEIGHT,
                    "essential": False,
                    "edge_family": "protein_to_complex",
                    "source_semantics": "exact_reactome_membership; not essentiality",
                },
            )
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError("source topology projection exceeds bounded graph limits")
    site_projection = _site_projection(bindings, complex_factors)
    edge_family_counts = {
        "protein_to_complex": sum(item["edge_family"] == "protein_to_complex" for item in edges.values()),
        "complex_to_pathway": sum(item["edge_family"] == "complex_to_pathway" for item in edges.values()),
    }
    topology = {
        "nodes": sorted(nodes.values(), key=lambda item: cast("str", item["node_id"])),
        "edges": sorted(edges.values(), key=lambda item: cast("str", item["edge_id"])),
    }
    topology_digest = "sha256:" + hashlib.sha256(_canonical_bytes(topology)).hexdigest()
    ablations = [
        {
            "edge_family": family,
            "omitted_edge_count": edge_family_counts[family],
            "interpretation": (
                "remove numerical source-to-complex concordance family"
                if family == "protein_to_complex"
                else "remove numerical complex-to-pathway concordance family"
            ),
        }
        for family in ("protein_to_complex", "complex_to_pathway")
    ]
    profile = {
        "model_id": MODEL_ID,
        "protein_edge_weight": PROTEIN_EDGE_WEIGHT,
        "pathway_edge_weight": PATHWAY_EDGE_WEIGHT,
        "max_nodes": MAX_NODES,
        "max_edges": MAX_EDGES,
        "site_parent_semantics": "annotation_only",
        "kinase_substrate_source": "absent; no kinase edges projected",
    }
    return {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:" + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": source_manifest,
        "source_complex_catalog_digest": source_catalog,
        "factor_receipts": {
            "complex": complex_receipt_digest,
            "pathway": pathway_receipt_digest,
        },
        "topology_digest": topology_digest,
        "topology": topology,
        "edge_family_counts": edge_family_counts,
        "edge_family_diagnostics": _edge_family_diagnostics(
            bindings, complex_factors, pathway_factors
        ),
        "ablations": ablations,
        "phosphosite_projection": site_projection,
        "semantics": {
            "numerical_edge_families": ["protein_to_complex", "complex_to_pathway"],
            "annotation_only_relations": ["phosphosite_site_of_parent_protein"],
            "unsupported_relations": ["kinase_substrate"],
            "claim_ceiling": "source-cohort concordance topology; not pathway activity, occupancy, kinase activity, or causality",
        },
        "factor_support": {
            "complexes": len(complex_factors),
            "jointly_observed_complexes": sum(
                factor.get("state") == "observed" for factor in complex_factors.values()
            ),
            "pathways": len(pathway_factors),
            "jointly_observed_pathways": sum(
                factor.get("state") == "observed" for factor in pathway_factors.values()
            ),
        },
        "limitations": [
            "The six-root topology is the exact closure of the admitted 28-complex panel, not the ten-root design target.",
            "Reactome membership is not essentiality, assembly, activity, flux, or causal regulation.",
            "Phosphosite parent links carry provenance only; no occupancy or localization confidence is inferred.",
            "No kinase-substrate source was captured, so kinase nodes and feedback edges are absent.",
        ],
    }


def build_projection(complex_receipt_path: Path, pathway_receipt_path: Path) -> dict[str, object]:
    complex_receipt = _receipt(complex_receipt_path)
    pathway_receipt = _receipt(pathway_receipt_path)
    source = complex_transition_source_catalog()
    return _build_projection(
        complex_receipt,
        pathway_receipt,
        source.complexes,
        complex_receipt_digest=_digest_bytes(complex_receipt_path),
        pathway_receipt_digest=_digest_bytes(pathway_receipt_path),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complex-receipt", type=Path, required=True)
    parser.add_argument("--pathway-receipt", type=Path, required=True)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    payload = build_projection(args.complex_receipt, args.pathway_receipt)
    args.destination.write_bytes(_canonical_bytes(payload))
    topology = cast("dict[str, object]", payload["topology"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "nodes": len(cast("list[object]", topology["nodes"])),
                "edges": len(cast("list[object]", topology["edges"])),
                "phosphosites": len(cast("list[object]", payload["phosphosite_projection"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
