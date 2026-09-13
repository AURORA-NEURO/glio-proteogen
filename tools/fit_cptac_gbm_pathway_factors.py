# ruff: noqa: E501, T201, TRY003
"""Fit source-locked pathway factors for the matched CPTAC GBM evidence lane.

The Reactome complex panel supplies exact direct pathway anchors.  This tool
projects the matched protein and protein-adjusted phosphosite modalities onto
those source-anchored roots using the same missing-aware robust factor solver.
It is intentionally caller-side: only aggregate loadings and provenance are
written, and the result is a concordance coordinate rather than pathway
activation, flux, or a causal claim.
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
from tools.build_cptac_gbm_adjusted_phosphosite_catalog import (
    MAX_ITERATIONS as ADJUSTED_MAX_ITERATIONS,
)
from tools.build_cptac_gbm_adjusted_phosphosite_catalog import (
    MIN_ADJUSTMENT_PAIRS,
    REGRESSION_RIDGE,
    ROBUST_SCALE_FLOOR,
    fit_parent_regression,
    read_phosphosite_matrix,
)
from tools.build_cptac_gbm_adjusted_phosphosite_catalog import (
    MODEL_ID as ADJUSTED_MODEL_ID,
)
from tools.build_cptac_gbm_matched_feature_catalog import (
    PHOSPHOSITE_FILENAME,
    PROTEIN_FILENAME,
    _group_indices,
    _metadata_from_manifest,
)
from tools.capture_cptac_gbm_matched_source_manifest import (
    MANIFEST_FILENAME,
    SAMPLE_MAP_FILES,
    _canonical_bytes,
    parse_sample_map,
    verify_local_files,
)
from tools.fit_cptac_gbm_complex_factors import (
    COORDINATE_RIDGE,
    DAMPING,
    FACTOR_MODEL_ID,
    HUBER_DELTA,
    MAX_ITERATIONS,
    RIDGE_TO_EQUAL,
    TOLERANCE,
    fit_rank_one,
    read_protein_matrix,
)

MODEL_ID: Final = "cptac-gbm-pathway-factors/1.0.0"
MIN_PATHWAY_PROTEINS: Final = 5
MIN_PATHWAY_SITES: Final = 8
MIN_PATHWAY_SITE_GENES: Final = 4


def _adjusted_site_rows(
    rows: list[dict[str, object]], genes: list[str], protein_matrix: np.ndarray
) -> tuple[list[dict[str, object]], dict[str, int]]:
    gene_index = {gene: index for index, gene in enumerate(genes)}
    adjusted: list[dict[str, object]] = []
    counts = {"rows": len(rows), "adjusted": 0, "missing": 0, "unsupported": 0}
    for row in rows:
        gene = cast("str | None", row.get("gene"))
        if row.get("organism") not in {None, "Homo sapiens"} or gene is None:
            counts["unsupported"] += 1
            continue
        parent = gene_index.get(gene)
        if parent is None:
            counts["unsupported"] += 1
            continue
        values = cast("np.ndarray", row["values"])
        if not np.any(np.isfinite(values)):
            counts["missing"] += 1
            continue
        try:
            fit = fit_parent_regression(protein_matrix[parent], values)
        except ValueError:
            counts["unsupported"] += 1
            continue
        adjusted.append(
            {
                "feature_id": row["feature_id"],
                "gene": gene,
                "residuals": fit.pop("residuals"),
                "paired_support": fit["paired_support"],
                "alpha": fit["alpha"],
                "beta": fit["beta"],
                "residual_scale": fit["residual_scale"],
                "trace_digest": fit["trace_digest"],
            }
        )
        counts["adjusted"] += 1
    return adjusted, counts


def _pathway_factor(
    binding_group: list[ReactomeComplexBinding],
    genes: list[str],
    protein_matrix: np.ndarray,
    adjusted_sites: list[dict[str, object]],
) -> dict[str, object]:
    pathway_id = binding_group[0].anchor_pathway.top_level_pathway_id
    pathway_name = binding_group[0].anchor_pathway.top_level_pathway_name
    complex_ids = sorted({binding.reactome_id for binding in binding_group})
    member_genes = sorted(
        {
            member.gene_symbol
            for binding in binding_group
            for member in binding.member_bindings
            if member.gene_symbol in set(genes)
        }
    )
    gene_index = {gene: index for index, gene in enumerate(genes)}
    protein_members = [gene for gene in member_genes if gene in gene_index]
    if len(protein_members) < MIN_PATHWAY_PROTEINS:
        return {
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
            "complex_ids": complex_ids,
            "state": "unsupported",
            "abstention_reason": f"fewer than {MIN_PATHWAY_PROTEINS} source protein genes",
            "protein_gene_count": len(protein_members),
        }
    protein_indices = [gene_index[gene] for gene in protein_members]
    site_members = [
        row
        for row in adjusted_sites
        if row["gene"] in set(protein_members)
        and cast("int", row["paired_support"]) >= MIN_ADJUSTMENT_PAIRS
    ]
    site_genes = {cast("str", row["gene"]) for row in site_members}
    if len(site_members) < MIN_PATHWAY_SITES:
        return {
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
            "complex_ids": complex_ids,
            "state": "unsupported",
            "abstention_reason": f"fewer than {MIN_PATHWAY_SITES} eligible phosphosite rows",
            "protein_gene_count": len(protein_members),
            "phosphosite_row_count": len(site_members),
            "phosphosite_parent_gene_count": len(site_genes),
        }
    if len(site_genes) < MIN_PATHWAY_SITE_GENES:
        return {
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
            "complex_ids": complex_ids,
            "state": "unsupported",
            "abstention_reason": (
                f"eligible phosphosite rows span fewer than {MIN_PATHWAY_SITE_GENES} parent genes"
            ),
            "protein_gene_count": len(protein_members),
            "phosphosite_row_count": len(site_members),
            "phosphosite_parent_gene_count": len(site_genes),
        }
    protein_factor = fit_rank_one(protein_matrix[protein_indices])
    site_factor = fit_rank_one(
        np.stack([cast("np.ndarray", row["residuals"]) for row in site_members])
    )
    site_loadings = cast("list[float]", site_factor["loadings"])
    return {
        "pathway_id": pathway_id,
        "pathway_name": pathway_name,
        "complex_ids": complex_ids,
        "state": "observed",
        "abstention_reason": None,
        "protein_gene_count": len(protein_members),
        "protein_members": protein_members,
        "protein_factor": protein_factor,
        "phosphosite_row_count": len(site_members),
        "phosphosite_parent_gene_count": len(site_genes),
        "phosphosite_features": [
            {
                "feature_id": row["feature_id"],
                "gene": row["gene"],
                "paired_support": row["paired_support"],
                "parent_alpha": row["alpha"],
                "parent_beta": row["beta"],
                "residual_scale": row["residual_scale"],
                "loading": loading,
                "parent_trace_digest": row["trace_digest"],
            }
            for row, loading in zip(site_members, site_loadings, strict=True)
        ],
        "phosphosite_factor": site_factor,
        "signal_semantics": "protein-adjusted relative phosphosite signal; not occupancy",
    }


def fit_panel(source_dir: Path, manifest_path: Path) -> dict[str, object]:
    paths = verify_local_files(source_dir)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    metadata = _metadata_from_manifest(manifest_path)
    labels, protein_map = parse_sample_map(paths[SAMPLE_MAP_FILES["PDC000204"]].read_bytes())
    phospho_labels, phospho_map = parse_sample_map(
        paths[SAMPLE_MAP_FILES["PDC000205"]].read_bytes()
    )
    if labels != phospho_labels:
        raise ValueError("protein and phosphosite sample maps do not share exact label order")
    _group_indices(labels, metadata)
    genes, protein_matrix, protein_oracles = read_protein_matrix(paths[PROTEIN_FILENAME], labels)
    phosphosite_rows, phosphosite_oracles = read_phosphosite_matrix(
        paths[PHOSPHOSITE_FILENAME], labels
    )
    adjusted_sites, adjustment_oracles = _adjusted_site_rows(
        phosphosite_rows, genes, protein_matrix
    )
    source = complex_transition_source_catalog()
    grouped: dict[str, list[ReactomeComplexBinding]] = {}
    for binding in source.complexes:
        grouped.setdefault(binding.anchor_pathway.top_level_pathway_id, []).append(binding)
    pathways = [
        _pathway_factor(grouped[pathway_id], genes, protein_matrix, adjusted_sites)
        for pathway_id in sorted(grouped)
    ]
    profile = {
        "model_id": MODEL_ID,
        "parent_adjustment_model": ADJUSTED_MODEL_ID,
        "parent_adjustment_profile": {
            "max_iterations": ADJUSTED_MAX_ITERATIONS,
            "min_adjustment_pairs": MIN_ADJUSTMENT_PAIRS,
            "regression_ridge": REGRESSION_RIDGE,
            "robust_scale_floor": ROBUST_SCALE_FLOOR,
        },
        "factor_model": FACTOR_MODEL_ID,
        "min_pathway_proteins": MIN_PATHWAY_PROTEINS,
        "min_pathway_sites": MIN_PATHWAY_SITES,
        "min_pathway_site_genes": MIN_PATHWAY_SITE_GENES,
        "huber_delta": HUBER_DELTA,
        "ridge_to_equal": RIDGE_TO_EQUAL,
        "coordinate_ridge": COORDINATE_RIDGE,
        "damping": DAMPING,
        "max_iterations": MAX_ITERATIONS,
        "tolerance": TOLERANCE,
    }
    return {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:" + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": manifest_digest,
        "source_complex_catalog_digest": source.content_digest,
        "sample_maps": {"protein": protein_map, "phosphoproteome": phospho_map},
        "matrix_oracles": {
            "protein": protein_oracles,
            "phosphosite": phosphosite_oracles,
            "adjustment": adjustment_oracles,
            "pathways": {
                "count": len(pathways),
                "observed": sum(item["state"] == "observed" for item in pathways),
                "unsupported": sum(item["state"] == "unsupported" for item in pathways),
            },
        },
        "pathways": pathways,
        "limitations": [
            "Caller-side aggregate loadings only; sample labels, matrix cells, scores, and residual vectors are not emitted.",
            "Pathway factors are source-cohort concordance coordinates and do not establish pathway activation, flux, direction, or causality.",
            "Protein-adjusted phosphosite residuals are not occupancy, localization confidence, stoichiometry, or biochemical kinase activity.",
            "Only six roots are represented by the admitted 28-complex source panel; absent source membership abstains rather than inventing edges.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or args.source_dir / MANIFEST_FILENAME
    payload = fit_panel(args.source_dir, manifest)
    args.destination.write_bytes(_canonical_bytes(payload))
    matrix_oracles = cast("dict[str, object]", payload["matrix_oracles"])
    pathway_oracles = cast("dict[str, object]", matrix_oracles["pathways"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "pathways": pathway_oracles["count"],
                "observed": pathway_oracles["observed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
