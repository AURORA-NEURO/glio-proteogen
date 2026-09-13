# ruff: noqa: C901, E501, PLR0915, T201, TRY003
"""Fit a caller-side protein-adjusted phosphosite catalog for matched CPTAC GBM.

The adapter joins each phosphosite row to its exact source ``Gene`` parent and
fits a robust Huber regression against the matched unshared protein ratio.  The
emitted value is a residual contrast (a protein-adjusted *relative* phosphosite
signal), never an occupancy or localization estimate.  Source cells remain
missing throughout; raw matrices, sample labels, and residual vectors stay in
the caller-owned process and are not written to the receipt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_cptac_gbm_matched_feature_catalog import (
    PHOSPHOSITE_FILENAME,
    PROTEIN_FILENAME,
    _contrast,
    _finite_float,
    _group_indices,
    _matrix_columns,
    _metadata_from_manifest,
)
from tools.capture_cptac_gbm_matched_source_manifest import (
    MANIFEST_FILENAME,
    SAMPLE_MAP_FILES,
    _canonical_bytes,
    parse_sample_map,
    verify_local_files,
)
from tools.fit_cptac_gbm_complex_factors import read_protein_matrix

MODEL_ID: Final = "cptac-gbm-protein-adjusted-phosphosite/1.0.0"
HUBER_DELTA: Final = 1.345
REGRESSION_RIDGE: Final = 0.01
ROBUST_SCALE_FLOOR: Final = 0.05
MAX_ITERATIONS: Final = 64
TOLERANCE: Final = 1.0e-9
DENOMINATOR_EPSILON: Final = 1.0e-12
MIN_ADJUSTMENT_PAIRS: Final = 8


def _huber_loss(residual: np.ndarray, delta: float = HUBER_DELTA) -> np.ndarray:
    absolute = np.abs(residual)
    return np.where(absolute <= delta, 0.5 * residual * residual, delta * (absolute - 0.5 * delta))


def _huber_weight(residual: np.ndarray, delta: float = HUBER_DELTA) -> np.ndarray:
    absolute = np.abs(residual)
    return np.where(absolute <= delta, 1.0, delta / np.maximum(absolute, 1.0e-15))


def _robust_scale(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return math.nan
    center = float(np.median(finite))
    mad = float(np.median(np.abs(finite - center)) * 1.4826)
    return max(mad, ROBUST_SCALE_FLOOR)


def _regression_objective(
    x: np.ndarray, y: np.ndarray, alpha: float, beta: float, scale: float
) -> float:
    residual = (y - alpha - beta * x) / scale
    return float(np.sum(_huber_loss(residual)) + REGRESSION_RIDGE * beta * beta)


def _theil_sen_start(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return a deterministic pairwise-median slope/intercept start."""

    slopes: list[float] = []
    for left in range(x.size):
        denominator = x[left + 1 :] - x[left]
        numerator = y[left + 1 :] - y[left]
        valid = np.abs(denominator) > DENOMINATOR_EPSILON
        slopes.extend((numerator[valid] / denominator[valid]).tolist())
    beta = float(np.median(np.asarray(slopes, dtype=np.float64))) if slopes else 0.0
    alpha = float(np.median(y - beta * x))
    return alpha, beta


def fit_parent_regression(
    protein: np.ndarray, phosphosite: np.ndarray
) -> dict[str, object]:
    """Fit one missing-aware robust parent-protein regression.

    The returned residual vector is deliberately available only to the caller
    while building the aggregate contrast.  It is not suitable for a public
    receipt and callers must drop it before serialization.
    """

    if protein.ndim != 1 or phosphosite.ndim != 1 or protein.size != phosphosite.size:
        raise ValueError("parent regression vectors must be one-dimensional and aligned")
    valid = np.isfinite(protein) & np.isfinite(phosphosite)
    support = int(np.sum(valid))
    if support < MIN_ADJUSTMENT_PAIRS:
        raise ValueError(f"fewer than {MIN_ADJUSTMENT_PAIRS} paired observations")
    x = protein[valid].astype(np.float64, copy=False)
    y = phosphosite[valid].astype(np.float64, copy=False)
    alpha, beta = _theil_sen_start(x, y)
    scale = _robust_scale(y - alpha - beta * x)
    if not math.isfinite(scale):
        raise ValueError("parent regression has no finite phosphosite values")
    trace: list[float] = []
    converged = False
    for _iteration in range(1, MAX_ITERATIONS + 1):
        residual = (y - alpha - beta * x) / scale
        weights = _huber_weight(residual)
        design = np.column_stack((np.ones_like(x), x))
        weighted_design = design * weights[:, None]
        normal = design.T @ weighted_design
        normal[1, 1] += REGRESSION_RIDGE
        rhs = design.T @ (weights * y)
        try:
            candidate = np.linalg.solve(normal, rhs)
        except np.linalg.LinAlgError:
            candidate = np.linalg.lstsq(normal, rhs, rcond=None)[0]
        candidate_alpha = float(candidate[0])
        candidate_beta = float(candidate[1])
        updated_alpha = 0.75 * candidate_alpha + 0.25 * alpha
        updated_beta = 0.75 * candidate_beta + 0.25 * beta
        objective = _regression_objective(x, y, updated_alpha, updated_beta, scale)
        if trace and objective > trace[-1] + 1.0e-10:
            backoff = 0.5
            while backoff >= 2.0**-18 and objective > trace[-1] + 1.0e-10:
                updated_alpha = backoff * updated_alpha + (1.0 - backoff) * alpha
                updated_beta = backoff * updated_beta + (1.0 - backoff) * beta
                objective = _regression_objective(x, y, updated_alpha, updated_beta, scale)
                backoff *= 0.5
            if objective > trace[-1] + 1.0e-10:
                raise ValueError("parent regression objective increased after backtracking")
        trace.append(objective)
        change = max(abs(updated_alpha - alpha), abs(updated_beta - beta))
        alpha, beta = updated_alpha, updated_beta
        if change <= TOLERANCE:
            converged = True
            break
    residuals = y - alpha - beta * x
    residual_scale = _robust_scale(residuals)
    if not math.isfinite(residual_scale) or not trace:
        raise ValueError("parent regression produced a non-finite fit")
    if any(right > left + 1.0e-10 for left, right in pairwise(trace)):
        raise ValueError("parent regression objective trace is not monotone")
    full_residual = np.full(protein.shape, np.nan, dtype=np.float64)
    full_residual[valid] = residuals
    quantized_trace = [round(float(value), 10) for value in trace]
    return {
        "alpha": round(alpha, 8),
        "beta": round(beta, 8),
        "residual_scale": round(residual_scale, 8),
        "paired_support": support,
        "objective_trace": quantized_trace,
        "trace_digest": "sha256:" + hashlib.sha256(_canonical_bytes(quantized_trace)).hexdigest(),
        "iterations": len(trace),
        "converged": converged,
        "huber_delta": HUBER_DELTA,
        "ridge": REGRESSION_RIDGE,
        "residuals": full_residual,
    }


def read_phosphosite_matrix(
    path: Path, labels: list[str]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read phosphosite rows and exact source annotations without splitting composites."""

    records: list[dict[str, object]] = []
    seen_feature_ids: set[str] = set()
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        if not header or header[0] != "Phosphosite":
            raise ValueError("unexpected CPTAC phosphosite matrix header")
        columns = _matrix_columns(header, labels, measure="Log Ratio")
        expected_width = len(header)
        if len(columns) != len(labels) or len(header) < len(columns) + 4:
            raise ValueError("phosphosite matrix does not contain expected matched columns")
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(f"ragged phosphosite matrix row {row_number}")
            row_count += 1
            row_id = row[0]
            if not row_id:
                raise ValueError(f"phosphosite row {row_number} has an empty feature identifier")
            if row_id in seen_feature_ids:
                raise ValueError(f"duplicate phosphosite feature identifier: {row_id}")
            seen_feature_ids.add(row_id)
            values = np.fromiter((_finite_float(row[index]) for index in columns), dtype=np.float64)
            records.append(
                {
                    "feature_id": row_id,
                    "gene": row[-2] or None,
                    "organism": row[-1] or None,
                    "values": values,
                }
            )
    if not records:
        raise ValueError("phosphosite matrix has no feature rows")
    return records, {
        "rows": row_count,
        "human": sum(item["organism"] in {None, "Homo sapiens"} for item in records),
        "nonhuman": sum(item["organism"] not in {None, "Homo sapiens"} for item in records),
        "annotated_gene": sum(item["gene"] is not None for item in records),
    }


def _unsupported(
    row: dict[str, object], reason: str, *, state: str = "unsupported"
) -> dict[str, object]:
    return {
        "feature_id": row["feature_id"],
        "gene": row["gene"],
        "parent_protein": row["gene"],
        "modality": "phosphoproteomics",
        "source_measure": "Log Ratio",
        "adjustment_model": "huber_parent_protein",
        "adjusted_signal_semantics": "protein-adjusted relative phosphosite signal; not occupancy",
        "state": state,
        "abstention_reason": reason,
        "paired_support": 0,
        "alpha": None,
        "beta": None,
        "residual_scale": None,
        "effect": None,
        "standard_error": None,
        "standardized_effect": None,
    }


def build_catalog(source_dir: Path, manifest_path: Path) -> dict[str, object]:
    """Build a private aggregate adjusted-phosphosite receipt from locked files."""

    paths = verify_local_files(source_dir)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    metadata = _metadata_from_manifest(manifest_path)
    labels, protein_map = parse_sample_map(paths[SAMPLE_MAP_FILES["PDC000204"]].read_bytes())
    phospho_labels, phospho_map = parse_sample_map(
        paths[SAMPLE_MAP_FILES["PDC000205"]].read_bytes()
    )
    if labels != phospho_labels:
        raise ValueError("protein and phosphosite sample maps do not share exact label order")
    tumor, normal, cohort = _group_indices(labels, metadata)
    genes, protein_matrix, protein_oracles = read_protein_matrix(paths[PROTEIN_FILENAME], labels)
    gene_index = {gene: index for index, gene in enumerate(genes)}
    phosphosite_rows, phosphosite_oracles = read_phosphosite_matrix(
        paths[PHOSPHOSITE_FILENAME], labels
    )
    features: list[dict[str, object]] = []
    for row in phosphosite_rows:
        gene = cast("str | None", row["gene"])
        if row["organism"] not in {None, "Homo sapiens"}:
            features.append(_unsupported(row, "source feature is not annotated as Homo sapiens"))
            continue
        if gene is None:
            features.append(_unsupported(row, "phosphosite row has no source gene annotation"))
            continue
        parent_index = gene_index.get(gene)
        if parent_index is None:
            features.append(_unsupported(row, "source gene has no matched unshared protein row"))
            continue
        phosphosite = cast("np.ndarray", row["values"])
        finite_site = int(np.sum(np.isfinite(phosphosite)))
        finite_parent = int(np.sum(np.isfinite(protein_matrix[parent_index])))
        if finite_site == 0:
            features.append(_unsupported(row, "no finite phosphosite observations", state="missing"))
            continue
        if finite_parent == 0:
            features.append(_unsupported(row, "parent protein has no finite observations"))
            continue
        try:
            fit = fit_parent_regression(protein_matrix[parent_index], phosphosite)
        except ValueError as exc:
            features.append(_unsupported(row, str(exc)))
            continue
        residuals = cast("np.ndarray", fit.pop("residuals"))
        contrast = _contrast(
            residuals[tumor],
            residuals[normal],
            row_id=cast("str", row["feature_id"]),
            gene=gene,
            modality="phosphoproteomics",
            source_measure="protein-adjusted Log Ratio residual",
        )
        contrast.update(
            {
                "parent_protein": gene,
                "adjustment_model": "huber_parent_protein",
                "adjusted_signal_semantics": "protein-adjusted relative phosphosite signal; not occupancy",
                "paired_support": fit["paired_support"],
                "alpha": fit["alpha"],
                "beta": fit["beta"],
                "residual_scale": fit["residual_scale"],
                "objective_trace": fit["objective_trace"],
                "trace_digest": fit["trace_digest"],
                "iterations": fit["iterations"],
                "converged": fit["converged"],
            }
        )
        features.append(contrast)
    oracle = {
        "rows": len(features),
        "observed": sum(item["state"] == "observed" for item in features),
        "missing": sum(item["state"] == "missing" for item in features),
        "unsupported": sum(item["state"] == "unsupported" for item in features),
        "adjusted": sum(item.get("adjustment_model") == "huber_parent_protein" for item in features),
    }
    source_files = {
        name: {
            "bytes": paths[name].stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(paths[name].read_bytes()).hexdigest(),
        }
        for name in (PROTEIN_FILENAME, PHOSPHOSITE_FILENAME)
    }
    profile = {
        "model_id": MODEL_ID,
        "huber_delta": HUBER_DELTA,
        "regression_ridge": REGRESSION_RIDGE,
        "robust_scale_floor": ROBUST_SCALE_FLOOR,
        "max_iterations": MAX_ITERATIONS,
        "tolerance": TOLERANCE,
        "min_adjustment_pairs": MIN_ADJUSTMENT_PAIRS,
    }
    payload: dict[str, object] = {
        "schema_version": MODEL_ID,
        "algorithm_profile": profile,
        "algorithm_profile_digest": "sha256:" + hashlib.sha256(_canonical_bytes(profile)).hexdigest(),
        "source_manifest_digest": manifest_digest,
        "source_files": source_files,
        "cohort": cohort,
        "sample_maps": {"protein": protein_map, "phosphoproteome": phospho_map},
        "measurement_semantics": {
            "protein_measure": "Unshared Log Ratio",
            "phosphosite_measure": "Log Ratio",
            "adjustment": "site_ratio = alpha + beta * matched_unshared_protein_ratio + robust residual",
            "output": "qualified primary-tumor minus qualified solid-tissue-normal contrast of residuals",
            "signal_name": "protein-adjusted relative phosphosite signal",
            "not_claimed": ["phosphosite occupancy", "site-localization confidence", "biochemical kinase activity"],
            "missingness": "blank cells remain missing; no imputation or censoring bound is inferred",
            "composite_phosphosite_policy": "source phosphosite rows remain atomic; peptide/site strings are not split",
            "uncertainty": "robust residual and group MAD scales are model-derived, not analytical replicate error",
        },
        "matrix_oracles": {
            "protein": protein_oracles,
            "phosphosite": phosphosite_oracles,
            "adjusted_features": oracle,
        },
        "features": features,
        "limitations": [
            "Caller-side aggregate contrasts only; sample labels, matrix cells, and residual vectors are not emitted.",
            "The residual removes a fitted parent-protein trend but does not estimate occupancy, localization, stoichiometry, or causal regulation.",
            "Source processing, uncertainty, licensing, nested case-group evaluation, and topology projection remain admission blockers.",
        ],
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or args.source_dir / MANIFEST_FILENAME
    payload = build_catalog(args.source_dir, manifest)
    args.destination.write_bytes(_canonical_bytes(payload))
    features = cast("list[object]", payload["features"])
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "features": len(features),
                "observed": payload["matrix_oracles"]["adjusted_features"]["observed"]
                if isinstance(payload["matrix_oracles"], dict)
                else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
