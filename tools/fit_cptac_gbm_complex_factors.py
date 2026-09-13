# ruff: noqa: C901, E501, PLR0915, PLR2004, T201, TRY003
"""Fit private robust source factors for the matched CPTAC GBM complex panel.

The factor fitter consumes the caller-owned protein matrix and the already
admitted Reactome complex membership catalog.  It uses missing-aware alternating
Huber updates with an equal-membership ridge, deterministic damping, objective
trace checks, and orientation.  Only aggregate loadings and diagnostics are
written; sample scores, identifiers, and matrix cells never leave the caller's
private directory.
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

from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
    complex_transition_source_catalog,
)
from tools.build_cptac_gbm_matched_feature_catalog import PROTEIN_FILENAME
from tools.capture_cptac_gbm_matched_source_manifest import (
    MANIFEST_FILENAME,
    SAMPLE_MAP_FILES,
    _canonical_bytes,
    parse_sample_map,
    verify_local_files,
)

FACTOR_MODEL_ID: Final = "cptac-gbm-complex-huber-factor/1.0.0"
HUBER_DELTA: Final = 1.345
RIDGE_TO_EQUAL: Final = 0.025
COORDINATE_RIDGE: Final = 0.075
DAMPING: Final = 0.72
MAX_ITERATIONS: Final = 128
TOLERANCE: Final = 1.0e-8
MIN_FEATURES: Final = 3


def _huber_loss(residual: np.ndarray, delta: float = HUBER_DELTA) -> np.ndarray:
    absolute = np.abs(residual)
    return np.where(absolute <= delta, 0.5 * residual * residual, delta * (absolute - 0.5 * delta))


def _huber_weight(residual: np.ndarray, delta: float = HUBER_DELTA) -> np.ndarray:
    absolute = np.abs(residual)
    return np.where(absolute <= delta, 1.0, delta / np.maximum(absolute, 1.0e-15))


def _factor_objective(
    matrix: np.ndarray, loadings: np.ndarray, scores: np.ndarray, equal: np.ndarray
) -> float:
    valid = np.isfinite(matrix)
    residual = np.where(valid, matrix - loadings[:, None] * scores[None, :], 0.0)
    fit = float(np.sum(_huber_loss(residual[valid])))
    ridge = RIDGE_TO_EQUAL * float(np.sum((loadings - equal) ** 2))
    coordinate = COORDINATE_RIDGE * float(np.sum(scores * scores)) / max(scores.size, 1)
    return fit + ridge + coordinate


def fit_rank_one(matrix: np.ndarray) -> dict[str, object]:
    """Fit one missing-aware rank-one factor and return aggregate diagnostics."""
    if matrix.ndim != 2 or matrix.shape[0] < MIN_FEATURES or matrix.shape[1] < 3:
        raise ValueError("a factor needs at least three features and three samples")
    valid = np.isfinite(matrix)
    if not np.any(valid):
        raise ValueError("factor has no finite observations")
    centers = np.nanmedian(matrix, axis=1)
    centered = matrix - centers[:, None]
    scales = np.nanmedian(np.abs(centered), axis=1) * 1.4826
    scales = np.maximum(np.where(np.isfinite(scales), scales, 0.0), 0.05)
    normalized = centered / scales[:, None]
    normalized = np.where(np.isfinite(normalized), normalized, 0.0)
    equal = np.full(matrix.shape[0], 1.0 / math.sqrt(matrix.shape[0]), dtype=np.float64)
    scores = np.mean(normalized, axis=0)
    score_scale = float(np.linalg.norm(scores))
    scores = scores / max(score_scale, 1.0e-12)
    loadings = equal.copy()
    trace: list[float] = []
    converged = False
    for _iteration in range(1, MAX_ITERATIONS + 1):
        candidate_loadings = np.empty_like(loadings)
        for feature_index in range(matrix.shape[0]):
            observed = valid[feature_index]
            z = scores[observed]
            x = normalized[feature_index, observed]
            residual = x - loadings[feature_index] * z
            weights = _huber_weight(residual)
            denominator = float(np.sum(weights * z * z) + RIDGE_TO_EQUAL)
            numerator = float(np.sum(weights * z * x) + RIDGE_TO_EQUAL * equal[feature_index])
            candidate_loadings[feature_index] = numerator / max(denominator, 1.0e-12)
        norm = float(np.linalg.norm(candidate_loadings))
        candidate_loadings /= max(norm, 1.0e-12)
        candidate_scores = np.empty_like(scores)
        for sample_index in range(matrix.shape[1]):
            observed = valid[:, sample_index]
            loading_vector = candidate_loadings[observed]
            x = normalized[observed, sample_index]
            residual = x - loading_vector * scores[sample_index]
            weights = _huber_weight(residual)
            denominator = float(
                np.sum(weights * loading_vector * loading_vector) + COORDINATE_RIDGE
            )
            numerator = float(np.sum(weights * loading_vector * x))
            candidate_scores[sample_index] = numerator / max(denominator, 1.0e-12)
        candidate_scores -= float(np.mean(candidate_scores))
        candidate_scores /= max(float(np.linalg.norm(candidate_scores)), 1.0e-12)
        if float(np.dot(candidate_loadings, equal)) < 0.0:
            candidate_loadings *= -1.0
            candidate_scores *= -1.0
        updated_loadings = DAMPING * candidate_loadings + (1.0 - DAMPING) * loadings
        updated_loadings /= max(float(np.linalg.norm(updated_loadings)), 1.0e-12)
        updated_scores = DAMPING * candidate_scores + (1.0 - DAMPING) * scores
        objective = _factor_objective(normalized, updated_loadings, updated_scores, equal)
        if trace and objective > trace[-1] + 1.0e-10:
            # A damped step must not make the robust objective worse.  Back off toward
            # the previous iterate deterministically rather than hiding non-convergence.
            backoff = 0.5
            while backoff >= 2.0**-18 and objective > trace[-1] + 1.0e-10:
                updated_loadings = backoff * updated_loadings + (1.0 - backoff) * loadings
                updated_scores = backoff * updated_scores + (1.0 - backoff) * scores
                objective = _factor_objective(normalized, updated_loadings, updated_scores, equal)
                backoff *= 0.5
            if objective > trace[-1] + 1.0e-10:
                raise ValueError(
                    "robust factor objective increased after deterministic backtracking"
                )
        trace.append(objective)
        change = max(
            float(np.max(np.abs(updated_loadings - loadings))),
            float(np.max(np.abs(updated_scores - scores))),
        )
        loadings, scores = updated_loadings, updated_scores
        if change <= TOLERANCE:
            converged = True
            break
    if not trace or any(not math.isfinite(item) for item in trace):
        raise ValueError("factor objective trace is non-finite")
    if any(right > left + 1.0e-10 for left, right in pairwise(trace)):
        raise ValueError("factor objective trace is not monotone")
    return {
        "loadings": [round(float(value), 8) for value in loadings],
        "feature_support": [int(value) for value in valid.sum(axis=1)],
        "sample_support": [int(value) for value in valid.sum(axis=0)],
        "objective_trace": [round(float(value), 10) for value in trace],
        "trace_digest": "sha256:" + hashlib.sha256(_canonical_bytes(trace)).hexdigest(),
        "iterations": len(trace),
        "converged": converged,
        "orientation": "nonnegative_dot_equal_membership",
        "ridge_to_equal": RIDGE_TO_EQUAL,
        "coordinate_ridge": COORDINATE_RIDGE,
        "huber_delta": HUBER_DELTA,
        "damping": DAMPING,
    }


def read_protein_matrix(
    path: Path, labels: list[str]
) -> tuple[list[str], np.ndarray, dict[str, object]]:
    """Read the unshared protein block while preserving source missingness."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        columns = [
            index
            for index, cell in enumerate(header[1:], start=1)
            if cell.endswith(" Unshared Log Ratio")
        ]
        observed_labels = [header[index][: -len(" Unshared Log Ratio")] for index in columns]
        if observed_labels != labels:
            raise ValueError("protein unshared columns do not match official sample-map order")
        genes: list[str] = []
        rows: list[np.ndarray] = []
        aggregate_rows = 0
        expected_width = len(header)
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(f"ragged protein matrix row {row_number}")
            gene = row[0]
            if gene in {"Mean", "Median", "StdDev"}:
                aggregate_rows += 1
                continue
            if not gene or gene in genes:
                raise ValueError(f"duplicate or empty protein feature: {gene}")
            genes.append(gene)
            values = np.fromiter(
                (math.nan if not row[index] else float(row[index]) for index in columns),
                dtype=np.float64,
                count=len(columns),
            )
            if not np.all(np.isfinite(values) | np.isnan(values)):
                raise ValueError(f"non-finite protein value in row {row_number}")
            rows.append(values)
    if not rows:
        raise ValueError("protein matrix has no biological features")
    matrix = np.stack(rows)
    return (
        genes,
        matrix,
        {
            "rows": len(rows) + aggregate_rows,
            "biological_features": len(genes),
            "aggregate_rows": aggregate_rows,
        },
    )


def fit_panel(source_dir: Path, manifest_path: Path) -> dict[str, object]:
    paths = verify_local_files(source_dir)
    labels, _ = parse_sample_map(paths[SAMPLE_MAP_FILES["PDC000204"]].read_bytes())
    genes, matrix, matrix_oracles = read_protein_matrix(paths[PROTEIN_FILENAME], labels)
    gene_index = {gene: index for index, gene in enumerate(genes)}
    source = complex_transition_source_catalog()
    factors: list[dict[str, object]] = []
    for complex_binding in source.complexes:
        members = [
            member.gene_symbol
            for member in complex_binding.member_bindings
            if member.gene_symbol in gene_index
        ]
        if len(members) < MIN_FEATURES:
            continue
        indices = [gene_index[member] for member in members]
        factor = fit_rank_one(matrix[indices])
        factors.append(
            {
                "complex_id": complex_binding.reactome_id,
                "domain_id": complex_binding.domain_id,
                "members": members,
                "member_count": len(members),
                "factor": factor,
            }
        )
    if not factors:
        raise ValueError("no selected Reactome complex has three source protein members")
    return {
        "schema_version": FACTOR_MODEL_ID,
        "source_manifest_digest": "sha256:"
        + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_complex_catalog_digest": source.content_digest,
        "matrix_oracles": matrix_oracles,
        "factors": factors,
        "limitations": [
            "Caller-side aggregate loadings only; sample scores and matrix cells are not emitted.",
            "Factors describe source-cohort protein concordance and do not establish complex assembly, activity, flux, or causality.",
            "The PDC common reference may be cohort-transductive; nested evaluation and processing approval remain required.",
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
    print(
        json.dumps(
            {
                "destination": str(args.destination),
                "bytes": args.destination.stat().st_size,
                "schema_version": payload["schema_version"],
                "factors": len(cast("list[object]", payload["factors"])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
