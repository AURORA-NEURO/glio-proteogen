# ruff: noqa: E501, T201
"""Run deterministic scientific-oracle checks for the matched GBM factor lane.

The oracle is deliberately synthetic: it constructs signed latent directions
with glioma pathway-like member sets, parent-protein trends, missing cells, and
gross outliers.  It verifies replay stability, robust parent adjustment, and
direction recovery of the same Huber rank-one solver used by the caller-side
source fit.  No private source bytes or patient-derived values are consumed.
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

from tools.build_cptac_gbm_adjusted_phosphosite_catalog import fit_parent_regression
from tools.capture_cptac_gbm_matched_source_manifest import _canonical_bytes
from tools.fit_cptac_gbm_complex_factors import fit_rank_one

ORACLE_ID: Final = "cptac-gbm-matched-synthetic-oracle/1.0.0"
SEED: Final = 271_828
SAMPLES: Final = 96
MIN_DIRECTION_COSINE: Final = 0.90
MAX_PARENT_SLOPE_ERROR: Final = 0.12
MISSING_FRACTION: Final = 0.10
MIN_SIGN_RECOVERY: Final = 0.90


def _synthetic_signed_factor() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEED)
    latent = rng.normal(0.0, 1.0, size=SAMPLES)
    true_loadings = np.asarray((0.80, -0.70, 0.65, -0.55, 0.45, -0.35), dtype=np.float64)
    true_loadings /= np.linalg.norm(true_loadings)
    matrix = true_loadings[:, None] * latent[None, :] + 0.12 * rng.normal(
        0.0, 1.0, size=(true_loadings.size, SAMPLES)
    )
    matrix[1, 7] += 8.0
    matrix[4, 52] -= 7.0
    matrix[rng.random(matrix.shape) < MISSING_FRACTION] = np.nan
    return true_loadings, matrix


def _parent_adjustment_oracle() -> dict[str, object]:
    rng = np.random.default_rng(SEED + 1)
    parent = rng.normal(0.0, 1.0, size=SAMPLES)
    site = 0.35 + 1.65 * parent + 0.12 * rng.normal(0.0, 1.0, size=SAMPLES)
    site[[11, 70]] += (15.0, -13.0)
    site[[4, 28, 91]] = np.nan
    first = fit_parent_regression(parent, site)
    second = fit_parent_regression(parent, site)
    residual_first = cast("np.ndarray", first["residuals"])
    residual_second = cast("np.ndarray", second["residuals"])
    replay_equal = all(
        first[key] == second[key] for key in first if key != "residuals"
    ) and np.array_equal(residual_first, residual_second, equal_nan=True)
    slope = cast("float", first["beta"])
    return {
        "true_slope": 1.65,
        "fitted_slope": slope,
        "absolute_slope_error": round(abs(slope - 1.65), 8),
        "paired_support": first["paired_support"],
        "replay_equal": replay_equal,
        "outlier_resistance": abs(slope - 1.65) <= MAX_PARENT_SLOPE_ERROR,
    }


def evaluate() -> dict[str, object]:
    true_loadings, matrix = _synthetic_signed_factor()
    first = fit_rank_one(matrix)
    second = fit_rank_one(matrix)
    fitted = np.asarray(cast("list[float]", first["loadings"]), dtype=np.float64)
    cosine = float(np.dot(true_loadings, fitted) / np.linalg.norm(true_loadings) / np.linalg.norm(fitted))
    true_signs = np.sign(true_loadings)
    fitted_signs = np.sign(fitted)
    sign_recovered = int(np.sum(true_signs == fitted_signs))
    parent = _parent_adjustment_oracle()
    result = {
        "oracle_id": ORACLE_ID,
        "seed": SEED,
        "samples": SAMPLES,
        "solver": {
            "replay_equal": first == second,
            "direction_cosine": round(cosine, 8),
            "direction_cosine_pass": cosine >= MIN_DIRECTION_COSINE,
            "signed_members": int(true_loadings.size),
            "signed_members_recovered": sign_recovered,
            "direction_recovery_fraction": round(sign_recovered / true_loadings.size, 8),
            "missing_fraction": MISSING_FRACTION,
            "gross_outliers": 2,
        },
        "parent_adjustment": parent,
        "pass": bool(
            first == second
            and cosine >= MIN_DIRECTION_COSINE
            and sign_recovered / true_loadings.size >= MIN_SIGN_RECOVERY
            and parent["replay_equal"]
            and parent["outlier_resistance"]
        ),
        "limitations": [
            "Synthetic recovery does not establish external validity or source-cohort performance.",
            "The oracle checks direction recovery and robust adjustment, not pathway activity or clinical prediction.",
        ],
    }
    result["oracle_digest"] = "sha256:" + hashlib.sha256(_canonical_bytes(result)).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = evaluate()
    args.destination.write_bytes(_canonical_bytes(result))
    print(json.dumps({"destination": str(args.destination), **result}, sort_keys=True))
    if not result["pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
