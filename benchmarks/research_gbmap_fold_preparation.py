"""Deterministic GBmap full-fold preparation regression benchmark."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from benchmarks._module_validation import run_pytest_benchmark
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.selection import (
    _build_reference_selection_cache,
)
from glio_proteogen.research.gbmap_deconvolution.splits import (
    build_validation_split_plan,
)
from glio_proteogen.research.gbmap_deconvolution.training import (
    _AbstainedFold,
    _prepare_fold,
    _PreparedFold,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS: Final = 0.45
EXPECTED_SEMANTIC_DIGEST: Final = (
    "sha256:8b44b9cbcba02ec5a9380d248f0925ba53fcf1d06d0959c859a0a2dc2e6705a8"
)
STUDY_COUNT: Final = 4
DONORS_PER_STUDY: Final = 10
LABEL_COUNT: Final = 4
GENE_COUNT: Final = 512
EXPECTED_FOLD_COUNT: Final = 9

pytestmark = pytest.mark.benchmark


@lru_cache(maxsize=1)
def _reference() -> AggregateReference:
    random = np.random.default_rng(20260830)
    labels = (
        "malignant-mesenchymal",
        "malignant-proneural",
        "myeloid",
        "vascular",
    )
    feature_ids = tuple(f"ENSG{index:011d}" for index in range(GENE_COUNT))
    records: list[DonorLabelAggregate] = []
    for study_index in range(STUDY_COUNT):
        for donor_index in range(DONORS_PER_STUDY):
            donor = f"study-{study_index}-donor-{donor_index:02d}"
            for label_index, label in enumerate(labels):
                weights = np.ones(GENE_COUNT, dtype=np.float64)
                marker_start = label_index * 32
                weights[marker_start : marker_start + 32] = 20.0
                study_start = 256 + study_index * 16
                weights[study_start : study_start + 16] *= 1.25
                counts = random.multinomial(20_000, weights / np.sum(weights))
                detected = np.minimum(counts, 80).astype(np.int32)
                records.append(
                    DonorLabelAggregate(
                        donor_key=donor,
                        study_key=f"study-{study_index}",
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=100,
                        gene_counts=np.asarray(counts, dtype=np.int64),
                        detected_cell_counts=detected,
                        total_umis=20_000,
                    )
                )
    return AggregateReference(
        feature_ids=feature_ids,
        gene_symbols=tuple(f"GENE_{index:03d}" for index in range(GENE_COUNT)),
        records=tuple(reversed(records)),
        source_file_sha256="sha256:" + "1" * 64,
        source_bytes=8_975_644_082,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )


def _prepare_all_folds() -> tuple[_PreparedFold | _AbstainedFold, ...]:
    reference = _reference()
    cache = _build_reference_selection_cache(reference)
    plan = build_validation_split_plan(reference)
    return tuple(_prepare_fold(reference, plan, fold, None, cache) for fold in plan.folds)


def _semantic_digest(
    prepared: tuple[_PreparedFold | _AbstainedFold, ...],
) -> str:
    document: list[dict[str, object]] = []
    for item in prepared:
        if isinstance(item, _AbstainedFold):
            document.append(
                {
                    "fold_id": item.fold.fold_id,
                    "state": "abstained",
                    "reason": item.reason,
                    "eligible_lineage_count": item.eligible_lineage_count,
                    "selected_feature_count": item.selected_feature_count,
                }
            )
            continue
        background_digest = hashlib.sha256(
            np.asarray(item.background, dtype="<f8").tobytes(order="C")
        ).hexdigest()
        document.append(
            {
                "fold_id": item.fold.fold_id,
                "state": "prepared",
                "feature_indices": item.feature_indices,
                "labels": item.labels,
                "stable_gene_counts": item.stable_gene_counts,
                "training_records": tuple(
                    (record.study_key, record.donor_key, record.modeled_label)
                    for record in item.training_records
                ),
                "held_records": tuple(
                    (record.study_key, record.donor_key, record.modeled_label)
                    for record in item.held_records
                ),
                "background_sha256": background_digest,
            }
        )
    payload = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def test_representative_gbmap_fold_preparation_latency(
    benchmark: BenchmarkFixture,
) -> None:
    """Time all validation-fold partitions, selection, and backgrounds."""

    prepared = benchmark(_prepare_all_folds)

    benchmark.extra_info.update(
        {
            "boundary": "immutable aggregate reference to all fold-local preparations",
            "record_count": STUDY_COUNT * DONORS_PER_STUDY * LABEL_COUNT,
            "fold_count": len(prepared),
            "gene_count": GENE_COUNT,
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert len(prepared) == EXPECTED_FOLD_COUNT
    assert all(isinstance(item, _PreparedFold) for item in prepared)
    assert _semantic_digest(prepared) == EXPECTED_SEMANTIC_DIGEST
    for item in prepared:
        assert isinstance(item, _PreparedFold)
        training_donors = {record.donor_key for record in item.training_records}
        held_donors = {record.donor_key for record in item.held_records}
        assert training_donors.isdisjoint(held_donors)
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS


def run_benchmark(iterations: int = 3) -> dict[str, object]:
    """Run the locked GBmap full-fold preparation workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-RESEARCH-GBMAP-FOLD-PREPARATION",
        workload=test_representative_gbmap_fold_preparation_latency,
        iterations=iterations,
        mean_budget_seconds=MEAN_BUDGET_SECONDS,
    )


__all__ = ["run_benchmark"]
