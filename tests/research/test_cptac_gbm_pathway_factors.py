from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import numpy as np

from tools import fit_cptac_gbm_pathway_factors as pathways

if TYPE_CHECKING:
    from glio_proteogen.research.longitudinal_gbm_complex_transition.source_catalog import (
        ReactomeComplexBinding,
    )


def _site_rows(genes: tuple[str, ...], *, support: int = 10) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, gene in enumerate(genes):
        rows.append(
            {
                "feature_id": f"S{index}",
                "gene": gene,
                "paired_support": support,
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
    return rows


def test_adjusted_site_rows_abstains_unmatched_and_keeps_missing() -> None:
    genes = ["EGFR"]
    protein = np.arange(10, dtype=float)[None, :]
    rows: list[dict[str, object]] = [
        {
            "feature_id": "S1",
            "gene": "EGFR",
            "organism": "Homo sapiens",
            "values": np.full(10, np.nan),
        },
        {
            "feature_id": "S2",
            "gene": "UNKNOWN",
            "organism": "Homo sapiens",
            "values": np.ones(10),
        },
    ]
    adjusted, counts = pathways._adjusted_site_rows(rows, genes, protein)
    assert adjusted == []
    assert counts == {"rows": 2, "adjusted": 0, "missing": 1, "unsupported": 1}


def test_pathway_factor_requires_four_parent_genes() -> None:
    bindings = [
        cast(
            "ReactomeComplexBinding",
            SimpleNamespace(
                reactome_id="R-HSA-1",
                anchor_pathway=SimpleNamespace(
                    top_level_pathway_id="R-HSA-ROOT",
                    top_level_pathway_name="Root",
                ),
                member_bindings=tuple(
                    SimpleNamespace(gene_symbol=gene) for gene in ("A", "B", "C")
                ),
            ),
        )
    ]
    result = pathways._pathway_factor(
        bindings,
        ["A", "B", "C"],
        np.ones((3, 10), dtype=float),
        _site_rows(tuple("A" for _ in range(8))),
    )
    assert result["state"] == "unsupported"
    assert "fewer than 5" in str(result["abstention_reason"])


def test_pathway_site_rows_retain_atomic_feature_ids() -> None:
    rows = _site_rows(("A", "B", "C", "D", "E", "F", "G", "H"))
    ids = [cast("str", row["feature_id"]) for row in rows]
    assert ids == [f"S{index}" for index in range(8)]
    assert all(";" not in identifier or identifier.startswith("S") for identifier in ids)
