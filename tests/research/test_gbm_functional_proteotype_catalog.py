"""Integrity and semantic checks for the aggregate Migliozzi source catalog."""

from __future__ import annotations

import statistics
from itertools import pairwise

import pytest

from glio_proteogen.research.gbm_functional_proteotype import catalog as catalog_module
from glio_proteogen.research.gbm_functional_proteotype.catalog import (
    EXPECTED_ARTIFACT_DIGEST,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_PATHWAY_CATALOG_DIGEST,
    EXPECTED_SIGNATURE_CATALOG_DIGEST,
    functional_proteotype_catalog,
    is_source_gene_symbol,
)


def test_catalog_locks_exact_source_counts_and_digests() -> None:
    catalog = functional_proteotype_catalog()

    assert catalog.artifact_digest == EXPECTED_ARTIFACT_DIGEST
    assert catalog.content_digest == EXPECTED_CONTENT_DIGEST
    assert catalog.signature_catalog_digest == EXPECTED_SIGNATURE_CATALOG_DIGEST
    assert catalog.pathway_catalog_digest == EXPECTED_PATHWAY_CATALOG_DIGEST
    assert tuple(catalog.axes) == ("GPM", "MTC", "NEU", "PPR")
    assert [len(catalog.axes[axis]) for axis in catalog.axes] == [150, 150, 150, 150]
    assert [
        len(catalog.source_cohort_pathway_context[axis]) for axis in catalog.axes
    ] == [243, 107, 272, 204]
    assert len(catalog.by_gene_symbol) == 600


def test_source_loading_uses_within_axis_median_and_preserves_source_order() -> None:
    catalog = functional_proteotype_catalog()
    for axis, proteins in catalog.axes.items():
        assert tuple(item.source_rank for item in proteins) == tuple(range(1, 151))
        assert all(
            left.source_mww_score >= right.source_mww_score
            for left, right in pairwise(proteins)
        )
        assert statistics.median(item.source_loading for item in proteins) == pytest.approx(
            1.0
        )
        assert all(item.axis == axis and item.source_loading > 0.0 for item in proteins)


def test_gene_symbol_is_the_only_runtime_identifier() -> None:
    catalog = functional_proteotype_catalog()
    differing = tuple(
        item
        for proteins in catalog.axes.values()
        for item in proteins
        if item.source_protein_label != item.gene_symbol
    )

    assert differing
    assert all(item.gene_symbol in catalog.by_gene_symbol for item in differing)
    assert any(
        item.source_protein_label not in catalog.by_gene_symbol
        for item in differing
    )
    assert is_source_gene_symbol("CSTA")
    assert not is_source_gene_symbol("not-a-source-gene")


def test_pathways_remain_source_context_and_are_not_forced_disjoint() -> None:
    catalog = functional_proteotype_catalog()
    contexts = catalog.source_cohort_pathway_context
    assert all(
        0.0 <= item.p_value <= item.q_value <= 0.05
        for rows in contexts.values()
        for item in rows
    )
    shared = {item.pathway for item in contexts["GPM"]} & {
        item.pathway for item in contexts["MTC"]
    }
    assert shared


def test_catalog_rejects_any_artifact_byte_change(monkeypatch: pytest.MonkeyPatch) -> None:
    original = catalog_module._resource_bytes()
    functional_proteotype_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: original + b" ")
    with pytest.raises(RuntimeError, match="artifact digest mismatch"):
        functional_proteotype_catalog()
    functional_proteotype_catalog.cache_clear()
