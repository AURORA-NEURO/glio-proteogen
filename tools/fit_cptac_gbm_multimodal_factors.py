# ruff: noqa: E501, PLR2004, T201, TRY003
"""Fit caller-side multimodal complex factors for the matched CPTAC GBM lane.

This stage joins the two source modalities only through exact human gene
symbols. Protein factors use the unshared protein block. Phosphosite factors
use the atomic row residuals from a robust parent-protein regression, so the
second modality is a protein-adjusted relative phosphosite signal rather than
an occupancy estimate. The receipt contains aggregate loadings and diagnostics,
never sample labels, matrix cells, or sample scores.
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

MODEL_ID: Final = "cptac-gbm-multimodal-complex-factors/1.0.0"
MIN_SITE_SUPPORT: Final = 8
MIN_SITE_ROWS: Final = 3
MIN_SITE_GENES: Final = 2


def _site_adjustments(
    rows: list[dict[str, object]],
    genes: list[str],
    protein_matrix: np.ndarray,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Fit parent regressions and retain residual vectors only in-process."""

    gene_index = {gene: index for index, gene in enumerate(genes)}
    adjusted: list[dict[str, object]] = []
    counts = {"rows": len(rows), "adjusted": 0, "missing": 0, "unsupported": 0}
    for row in rows:
        gene = cast("str | None", row.get("gene"))
        if row.get("organism") not in {None, "Homo sapiens"}:
            counts["unsupported"] += 1
            continue
        if gene is None or gene not in gene_index:
            counts["unsupported"] += 1
            continue
        values = cast("np.ndarray", row["values"])
        if not np.any(np.isfinite(values)):
            counts["missing"] += 1
            continue
        try:
            fit = fit_parent_regression(protein_matrix[gene_index[gene]], values)
        except ValueError:
            counts["unsupported"] += 1
            continue
        residuals = cast("np.ndarray", fit.pop("residuals"))
        adjusted.append(
            {
                "feature_id": row["feature_id"],
                "gene": gene,
                "residuals": residuals,
                "paired_support": fit["paired_support"],
                "alpha": fit["alpha"],
                "beta": fit["beta"],
                "residual_scale": fit["residual_scale"],
                "trace_digest": fit["trace_digest"],
            }
        )
        counts["adjusted"] += 1
    return adjusted, counts


def _site_factor(
    rows: list[dict[str, object]],
    member_genes: set[str],
) -> tuple[dict[str, object] | None, str | None]:
    selected = [
        row
        for row in rows
        if row["gene"] in member_genes and cast("int", row["paired_support"]) >= MIN_SITE_SUPPORT
    ]
    selected_genes = {cast("str", row["gene"]) for row in selected}
    if len(selected) < MIN_SITE_ROWS:
        return None, f"fewer than {MIN_SITE_ROWS} eligible phosphosite rows"
    if len(selected_genes) < MIN_SITE_GENES:
        return None, f"eligible phosphosite rows span fewer than {MIN_SITE_GENES} parent genes"
    matrix = np.stack([cast("np.ndarray", row["residuals"]) for row in selected])
    factor = fit_rank_one(matrix)
    loadings = cast("list[float]", factor["loadings"])
    site_projection = [
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
        for row, loading in zip(selected, loadings, strict=True)
    ]
    return {
        "feature_count": len(selected),
        "parent_gene_count": len(selected_genes),
        "features": site_projection,
        "factor": factor,
        "signal_semantics": "protein-adjusted relative phosphosite signal; not occupancy",
    }, None


def _complex_factor(
    binding: ReactomeComplexBinding,
    genes: list[str],
    protein_matrix: np.ndarray,
    adjusted_sites: list[dict[str, object]],
) -> dict[str, object]:
    gene_set = set(genes)
    member_genes = {
        member.gene_symbol for member in binding.member_bindings if member.gene_symbol in gene_set
    }
    gene_index = {gene: index for index, gene in enumerate(genes)}
    ordered_genes = sorted(member_genes)
    protein_indices = [gene_index[gene] for gene in ordered_genes]
    if len(ordered_genes) < 3:
        return {
            "complex_id": binding.reactome_id,
            "domain_id": binding.domain_id,
            "state": "unsupported",
            "abstention_reason": "fewer than three source protein member genes",
            "protein_member_count": len(ordered_genes),
            "phosphosite": None,
        }
    protein_factor = fit_rank_one(protein_matrix[protein_indices])
    phosphosite, reason = _site_factor(adjusted_sites, set(ordered_genes))
    return {
        "complex_id": binding.reactome_id,
        "domain_id": binding.domain_id,
        "state": "observed" if phosphosite is not None else "unsupported",
        "abstention_reason": reason,
        "protein_member_count": len(ordered_genes),
        "protein_members": ordered_genes,
        "protein_factor": protein_factor,
        "phosphosite": phosphosite,
    }


def fit_panel(source_dir: Path, manifest_path: Path) -> dict[str, object]:
    """Fit protein and adjusted-phosphosite factors against the source panel."""

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
    genes, protein_matrix, protein_oracles = read_protein_matrix(
        paths[PROTEIN_FILENAME], labels
    )
    phosphosite_rows, phosphosite_oracles = read_phosphosite_matrix(
        paths[PHOSPHOSITE_FILENAME], labels
    )
    adjusted_sites, adjustment_oracles = _site_adjustments(
        phosphosite_rows, genes, protein_matrix
    )
    source = complex_transition_source_catalog()
    factors = [
        _complex_factor(binding, genes, protein_matrix, adjusted_sites)
        for binding in source.complexes
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
        "min_site_support": MIN_SITE_SUPPORT,
        "min_site_rows": MIN_SITE_ROWS,
        "min_site_parent_genes": MIN_SITE_GENES,
        "huber_delta": HUBER_DELTA,
        "ridge_to_equal": RIDGE_TO_EQUAL,
        "coordinate_ridge": COORDINATE_RIDGE,
        "damping": DAMPING,
        "max_iterations": MAX_ITERATIONS,
        "tolerance": TOLERANCE,
    }
    source_files = {
        name: {
            "bytes": paths[name].stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(paths[name].read_bytes()).hexdigest(),
        }
        for name in (
            PROTEIN_FILENAME,
            PHOSPHOSITE_FILENAME,
        )
    }
    return {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:" + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": manifest_digest,
        "source_complex_catalog_digest": source.content_digest,
        "source_files": source_files,
        "sample_maps": {"protein": protein_map, "phosphoproteome": phospho_map},
        "matrix_oracles": {
            "protein": protein_oracles,
            "phosphosite": phosphosite_oracles,
            "adjustment": adjustment_oracles,
            "factors": {
                "complexes": len(factors),
                "observed": sum(item["state"] == "observed" for item in factors),
                "unsupported": sum(item["state"] == "unsupported" for item in factors),
            },
        },
        "factors": factors,
        "limitations": [
            "Caller-side aggregate loadings only; sample labels, matrix cells, scores, and residual vectors are not emitted.",
            "Protein-adjusted residuals represent relative phosphosite signal after parent-protein trend removal; they are not occupancy, localization, stoichiometry, assembly, or causal regulation.",
            "Reactome membership supplies a fixed concordance set and does not establish complex activity or pathway flux.",
            "Source processing, nested case-group evaluation, uncertainty semantics, licensing, and topology admission remain required.",
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
    factor_oracles = cast("dict[str, object]", matrix_oracles["factors"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "complexes": factor_oracles["complexes"],
                "observed": factor_oracles["observed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
