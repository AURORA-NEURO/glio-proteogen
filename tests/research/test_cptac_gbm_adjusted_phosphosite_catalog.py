from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from tools import build_cptac_gbm_adjusted_phosphosite_catalog as adjusted

if TYPE_CHECKING:
    from pathlib import Path


def test_parent_regression_recovers_signal_and_is_replay_stable() -> None:
    protein = np.arange(12, dtype=float) / 3.0
    phosphosite = 0.7 + 1.8 * protein
    phosphosite[4] += 30.0
    phosphosite[9] = np.nan
    first = adjusted.fit_parent_regression(protein, phosphosite)
    second = adjusted.fit_parent_regression(protein, phosphosite)
    assert {key: value for key, value in first.items() if key != "residuals"} == {
        key: value for key, value in second.items() if key != "residuals"
    }
    assert np.array_equal(
        cast("np.ndarray", first["residuals"]),
        cast("np.ndarray", second["residuals"]),
        equal_nan=True,
    )
    assert abs(cast("float", first["beta"]) - 1.8) < 0.08
    assert abs(cast("float", first["alpha"]) - 0.7) < 0.2
    assert cast("int", first["paired_support"]) == 11
    assert cast("str", first["trace_digest"]).startswith("sha256:")
    residuals = cast("np.ndarray", first["residuals"])
    assert np.isnan(residuals[9])
    trace = cast("list[float]", first["objective_trace"])
    assert all(right <= left + 1.0e-8 for left, right in pairwise(trace))


def test_parent_regression_requires_paired_support() -> None:
    protein = np.arange(7, dtype=float)
    phosphosite = protein.copy()
    phosphosite[:2] = np.nan
    with pytest.raises(ValueError, match="fewer than"):
        adjusted.fit_parent_regression(protein, phosphosite)


def test_read_phosphosite_matrix_preserves_composites_and_blanks(tmp_path: Path) -> None:
    labels = ["A", "B", "C"]
    header = [
        "Phosphosite",
        *(f"{label} Log Ratio" for label in labels),
        "Peptide",
        "Gene",
        "Organism",
    ]
    path = tmp_path / "phosphosite.tsv"
    path.write_text(
        "\n".join(
            [
                "\t".join(header),
                "EGFR.Y1068;Y1173\t1\t\t-1\tPEP;PEP2\tEGFR\tHomo sapiens",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    records, oracle = adjusted.read_phosphosite_matrix(path, labels)
    assert records[0]["feature_id"] == "EGFR.Y1068;Y1173"
    assert records[0]["gene"] == "EGFR"
    values = cast("np.ndarray", records[0]["values"])
    assert np.isnan(values[1])
    assert oracle == {"rows": 1, "human": 1, "nonhuman": 0, "annotated_gene": 1}


def test_read_phosphosite_matrix_rejects_duplicate_and_wrong_order(tmp_path: Path) -> None:
    labels = ["A", "B"]
    path = tmp_path / "phosphosite.tsv"
    path.write_text(
        "Phosphosite\tB Log Ratio\tA Log Ratio\tPeptide\tGene\tOrganism\n"
        "S\t1\t2\tP\tG\tHomo sapiens\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sample-map order"):
        adjusted.read_phosphosite_matrix(path, labels)
    path.write_text(
        "Phosphosite\tA Log Ratio\tB Log Ratio\tPeptide\tGene\tOrganism\n"
        "S\t1\t2\tP\tG\tHomo sapiens\nS\t1\t2\tP\tG\tHomo sapiens\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        adjusted.read_phosphosite_matrix(path, labels)


def test_unsupported_preserves_explicit_relative_signal_semantics() -> None:
    result = adjusted._unsupported(
        {"feature_id": "S", "gene": None}, "phosphosite row has no source gene annotation"
    )
    assert result["state"] == "unsupported"
    assert result["effect"] is None
    assert "not occupancy" in str(result["adjusted_signal_semantics"])
