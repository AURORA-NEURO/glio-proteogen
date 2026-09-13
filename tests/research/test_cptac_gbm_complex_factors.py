from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from tools import fit_cptac_gbm_complex_factors as factors

if TYPE_CHECKING:
    from pathlib import Path


def test_huber_loss_and_weight_are_quadratic_then_linear() -> None:
    residual = np.asarray([-2.0, 0.0, 2.0])
    loss = factors._huber_loss(residual, delta=1.0)
    weight = factors._huber_weight(residual, delta=1.0)
    assert np.allclose(loss, [1.5, 0.0, 1.5])
    assert np.allclose(weight, [0.5, 1.0, 0.5])


def test_fit_rank_one_is_deterministic_and_oriented() -> None:
    matrix = np.asarray(
        [
            [1.0, 2.0, 3.0, np.nan, 5.0],
            [2.0, 4.0, 6.0, 8.0, 10.0],
            [1.5, 3.0, 4.5, 6.0, np.nan],
        ]
    )
    first = factors.fit_rank_one(matrix)
    second = factors.fit_rank_one(matrix)
    assert first == second
    assert len(cast("list[float]", first["loadings"])) == 3
    assert cast("int", first["iterations"]) >= 1
    assert cast("str", first["trace_digest"]).startswith("sha256:")
    trace = cast("list[float]", first["objective_trace"])
    assert all(right <= left + 1.0e-8 for left, right in pairwise(trace))


@pytest.mark.parametrize(
    "matrix",
    [np.ones((2, 4)), np.ones((3, 2)), np.full((3, 4), np.nan)],
)
def test_fit_rank_one_rejects_insufficient_or_empty_matrix(matrix: np.ndarray) -> None:
    with pytest.raises(ValueError):
        factors.fit_rank_one(matrix)


def test_read_protein_matrix_preserves_missingness_and_skips_aggregates(tmp_path: Path) -> None:
    labels = ["A", "B"]
    header = ["Gene", "A Unshared Log Ratio", "B Unshared Log Ratio", "Metadata"]
    path = tmp_path / "protein.tsv"
    path.write_text(
        "\n".join(
            [
                "\t".join(header),
                "Mean\t0\t0\t",
                "EGFR\t1\t\t",
                "PTEN\t-1\t-2\t",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    genes, matrix, oracle = factors.read_protein_matrix(path, labels)
    assert genes == ["EGFR", "PTEN"]
    assert np.isnan(matrix[0, 1])
    assert oracle == {"rows": 3, "biological_features": 2, "aggregate_rows": 1}


def test_read_protein_matrix_rejects_wrong_column_order(tmp_path: Path) -> None:
    path = tmp_path / "protein.tsv"
    path.write_text("Gene\tB Unshared Log Ratio\tA Unshared Log Ratio\nX\t1\t2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sample-map order"):
        factors.read_protein_matrix(path, ["A", "B"])
