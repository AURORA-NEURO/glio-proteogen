from __future__ import annotations

from typing import cast

import numpy as np

from tools import fit_cptac_gbm_multimodal_factors as multimodal


def test_site_adjustments_keep_only_exact_human_parent_pairs() -> None:
    genes = ["EGFR", "PTEN"]
    protein = np.asarray(
        [
            np.arange(12, dtype=float),
            np.arange(12, dtype=float) * -0.5,
        ]
    )
    rows = [
        {
            "feature_id": "EGFR.Y1068;Y1173",
            "gene": "EGFR",
            "organism": "Homo sapiens",
            "values": 0.3 + 1.2 * protein[0],
        },
        {
            "feature_id": "UNKNOWN.S1",
            "gene": "UNKNOWN",
            "organism": "Homo sapiens",
            "values": np.ones(12),
        },
        {
            "feature_id": "MOUSE.S1",
            "gene": "EGFR",
            "organism": "Mus musculus",
            "values": np.ones(12),
        },
    ]
    adjusted, counts = multimodal._site_adjustments(rows, genes, protein)
    assert [item["feature_id"] for item in adjusted] == ["EGFR.Y1068;Y1173"]
    assert counts == {"rows": 3, "adjusted": 1, "missing": 0, "unsupported": 2}
    residuals = cast("np.ndarray", adjusted[0]["residuals"])
    assert residuals.shape == (12,)
    assert cast("int", adjusted[0]["paired_support"]) == 12


def test_site_factor_requires_multiple_parent_genes() -> None:
    rows = [
        {
            "feature_id": f"S{index}",
            "gene": "EGFR",
            "paired_support": 10,
            "residuals": np.arange(10, dtype=float) + index,
            "alpha": 0.0,
            "beta": 1.0,
            "residual_scale": 0.1,
            "trace_digest": "sha256:test",
        }
        for index in range(3)
    ]
    factor, reason = multimodal._site_factor(rows, {"EGFR", "PTEN"})
    assert factor is None
    assert reason == "eligible phosphosite rows span fewer than 2 parent genes"


def test_site_factor_emits_loadings_without_sample_values() -> None:
    rows = []
    for index, gene in enumerate(("EGFR", "EGFR", "PTEN", "PTEN")):
        rows.append(
            {
                "feature_id": f"S{index}",
                "gene": gene,
                "paired_support": 10,
                "residuals": np.asarray(
                    [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, np.nan, 8.0, 9.0, 10.0]
                )
                + index * 0.1,
                "alpha": 0.0,
                "beta": 1.0,
                "residual_scale": 0.2,
                "trace_digest": "sha256:test",
            }
        )
    factor, reason = multimodal._site_factor(rows, {"EGFR", "PTEN"})
    assert reason is None
    assert factor is not None
    assert factor["feature_count"] == 4
    assert factor["parent_gene_count"] == 2
    feature = cast("list[dict[str, object]]", factor["features"])[0]
    assert "loading" in feature
    assert "residuals" not in feature
