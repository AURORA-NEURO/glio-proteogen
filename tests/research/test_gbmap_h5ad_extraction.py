from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbmap_deconvolution import (
    EXPECTED_DONOR_CATEGORY_SET_DIGEST,
    EXPECTED_H5PY_VERSION,
    PRODUCTION_SOURCE_DONOR_CATEGORIES,
    ExactGbmapH5adLock,
    GbmapDonorCrosswalk,
    GbmapDonorCrosswalkRule,
    GbmapExtractionError,
    GbmapExtractionReceipt,
    GbmapExtractionRecipe,
    GbmapLabelTaxonomy,
    GbmapSourceAdmissionError,
    GbmapStudyCrosswalk,
    GbmapStudyCrosswalkRule,
    GbmapTaxonomyRule,
    SparseCountBlock,
    aggregate_sparse_count_blocks,
    development_profile,
    donor_category_set_digest,
    extract_pinned_gbmap_reference,
    fingerprint_gbmap_source,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_study_crosswalk,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

if TYPE_CHECKING:
    from pathlib import Path

DIGEST_A = "sha256:" + "a" * 64

FEATURES = ("G1", "G2", "G3")
GENE_SYMBOLS = (None, None, None)
DONORS = ("d1a", "d1b", "d2", "d2", "d3")
STUDIES = ("sA", "sA", "sB1", "sB2", "sC")
LABELS = ("L1", "L2", "L1", "L1", "EX")
INDPTR = np.asarray([0, 2, 3, 3, 5, 6], dtype=np.int64)
INDICES = np.asarray([0, 2, 1, 0, 1, 2], dtype=np.int64)
COUNTS = np.asarray([2, 1, 3, 4, 1, 5], dtype=np.float32)


def _taxonomy() -> GbmapLabelTaxonomy:
    return GbmapLabelTaxonomy(
        taxonomy_id="tiny-taxonomy/1.0.0",
        rules=(
            GbmapTaxonomyRule(source_label="L1", modeled_label="lineage-1"),
            GbmapTaxonomyRule(source_label="L2", modeled_label="lineage-2"),
            GbmapTaxonomyRule(source_label="EX", exclusion_reason="outside_model_scope"),
        ),
    )


def _donor_crosswalk() -> GbmapDonorCrosswalk:
    return GbmapDonorCrosswalk(
        crosswalk_id="tiny-donors/1.0.0",
        rules=(
            GbmapDonorCrosswalkRule(source_donor_category="d1a", grouped_donor_key="d1"),
            GbmapDonorCrosswalkRule(source_donor_category="d1b", grouped_donor_key="d1"),
            GbmapDonorCrosswalkRule(source_donor_category="d2", grouped_donor_key="d2"),
            GbmapDonorCrosswalkRule(source_donor_category="d3", grouped_donor_key="d3"),
        ),
    )


def _study_crosswalk() -> GbmapStudyCrosswalk:
    return GbmapStudyCrosswalk(
        crosswalk_id="tiny-studies/1.0.0",
        rules=(
            GbmapStudyCrosswalkRule(source_study_category="sA", grouped_study_key="study-a"),
            GbmapStudyCrosswalkRule(source_study_category="sB1", grouped_study_key="study-b"),
            GbmapStudyCrosswalkRule(source_study_category="sB2", grouped_study_key="study-b"),
            GbmapStudyCrosswalkRule(source_study_category="sC", grouped_study_key="study-c"),
        ),
    )


def _recipe(*, row_block_size: int = 2, legacy: bool = True) -> GbmapExtractionRecipe:
    category_root = "obs/__categories/" if legacy else None
    return GbmapExtractionRecipe(
        source_profile="generic_fixture",
        matrix_path="layers/counts",
        donor_path="obs/patient",
        donor_categories_path=(None if category_root is None else f"{category_root}patient"),
        study_path="obs/author",
        study_categories_path=(None if category_root is None else f"{category_root}author"),
        source_label_path="obs/CellID",
        source_label_categories_path=(None if category_root is None else f"{category_root}CellID"),
        feature_id_path="var/_index",
        gene_symbol_path=None,
        expected_cell_count=5,
        expected_feature_count=3,
        expected_source_donor_category_count=4,
        expected_grouped_donor_category_count=3,
        expected_source_study_category_count=4,
        expected_grouped_study_count=3,
        expected_source_label_count=3,
        expected_grouped_donor_category_set_digest=None,
        reviewed_donor_crosswalk_digest=_donor_crosswalk().crosswalk_digest,
        reviewed_study_crosswalk_digest=_study_crosswalk().crosswalk_digest,
        reviewed_label_taxonomy_digest=_taxonomy().taxonomy_digest,
        expected_nnz=6,
        row_block_size=row_block_size,
    )


def _blocks(*, block_size: int = 2) -> tuple[SparseCountBlock, ...]:
    blocks: list[SparseCountBlock] = []
    for start in range(0, len(DONORS), block_size):
        end = min(len(DONORS), start + block_size)
        entry_start = int(INDPTR[start])
        entry_end = int(INDPTR[end])
        blocks.append(
            SparseCountBlock(
                row_start=start,
                donor_keys=DONORS[start:end],
                study_keys=STUDIES[start:end],
                source_labels=LABELS[start:end],
                indptr=np.asarray(INDPTR[start : end + 1] - entry_start),
                indices=np.asarray(INDICES[entry_start:entry_end]),
                data=np.asarray(COUNTS[entry_start:entry_end]),
            )
        )
    return tuple(blocks)


def _aggregate(*, block_size: int = 2):
    return aggregate_sparse_count_blocks(
        blocks=_blocks(block_size=block_size),
        feature_ids=FEATURES,
        gene_symbols=GENE_SYMBOLS,
        source_sha256=DIGEST_A,
        source_bytes=123,
        taxonomy=_taxonomy(),
        donor_crosswalk=_donor_crosswalk(),
        study_crosswalk=_study_crosswalk(),
        recipe=_recipe(row_block_size=block_size),
    )


def _record_projection(result) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            record.donor_key,
            record.study_key,
            record.modeled_label,
            record.source_labels,
            record.cell_count,
            tuple(int(value) for value in record.gene_counts),
            tuple(int(value) for value in record.detected_cell_counts),
            record.total_umis,
        )
        for record in result.reference.records
    )


def _write_legacy_fixture(path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    text_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as handle:
        layers = handle.create_group("layers")
        counts = layers.create_group("counts")
        counts.attrs["encoding-type"] = "csr_matrix"
        counts.attrs["encoding-version"] = "0.1.0"
        counts.attrs["shape"] = np.asarray([5, 3], dtype=np.int64)
        counts.create_dataset("data", data=COUNTS.astype(np.float32))
        counts.create_dataset("indices", data=INDICES.astype(np.int32))
        counts.create_dataset("indptr", data=INDPTR.astype(np.int32))

        var = handle.create_group("var")
        var.create_dataset("_index", data=np.asarray(FEATURES, dtype=text_dtype))
        obs = handle.create_group("obs")
        categories = obs.create_group("__categories")
        _write_legacy_category(obs, categories, "patient", DONORS, text_dtype)
        _write_legacy_category(obs, categories, "author", STUDIES, text_dtype)
        _write_legacy_category(obs, categories, "CellID", LABELS, text_dtype)


def _write_legacy_category(
    obs: Any,
    categories: Any,
    name: str,
    values: tuple[str, ...],
    text_dtype: Any,
) -> None:
    vocabulary = tuple(dict.fromkeys(values))
    lookup = {value: index for index, value in enumerate(vocabulary)}
    category_dataset = categories.create_dataset(
        name, data=np.asarray(vocabulary, dtype=text_dtype)
    )
    category_dataset.attrs["ordered"] = False
    codes = obs.create_dataset(
        name,
        data=np.asarray([lookup[value] for value in values], dtype=np.int8),
    )
    codes.attrs["categories"] = category_dataset.ref


def _lock_for(path: Path) -> ExactGbmapH5adLock:
    fingerprint = fingerprint_gbmap_source(path)
    assert not fingerprint.admission_granted
    return ExactGbmapH5adLock(
        source_id="tiny-gbmap-fixture",
        expected_bytes=fingerprint.source_bytes,
        md5=fingerprint.md5,
        sha256=fingerprint.sha256,
    )


def test_sparse_aggregation_exactly_conserves_counts_and_groups_sources() -> None:
    result = _aggregate()

    assert _record_projection(result) == (
        ("d1", "study-a", "lineage-1", ("L1",), 1, (2, 0, 1), (1, 0, 1), 3),
        ("d1", "study-a", "lineage-2", ("L2",), 1, (0, 3, 0), (0, 1, 0), 3),
        ("d2", "study-b", "lineage-1", ("L1",), 2, (4, 1, 0), (1, 1, 0), 5),
    )
    receipt = result.receipt
    assert receipt.cell_count == 5
    assert receipt.retained_cell_count == 4
    assert receipt.explicitly_excluded_cell_count == 1
    assert receipt.source_donor_category_count == 4
    assert receipt.grouped_donor_category_count == 3
    assert receipt.source_study_category_count == 4
    assert receipt.grouped_study_count == 3
    assert receipt.source_label_count == 3
    assert receipt.modeled_label_count == 2
    assert receipt.record_count == 3


def test_sparse_aggregation_is_chunk_boundary_invariant() -> None:
    one_row = _aggregate(block_size=1)
    three_rows = _aggregate(block_size=3)

    assert _record_projection(one_row) == _record_projection(three_rows)
    assert one_row.reference.feature_order_digest == three_rows.reference.feature_order_digest


@pytest.mark.parametrize(
    ("indices", "data", "match"),
    [
        (np.asarray([1, 1]), np.asarray([1, 2]), "strictly increasing"),
        (np.asarray([2, 1]), np.asarray([1, 2]), "strictly increasing"),
        (np.asarray([0]), np.asarray([0]), "explicit sparse zero"),
        (np.asarray([0]), np.asarray([-1]), "negative count"),
        (np.asarray([0]), np.asarray([1.5]), "fractional count"),
        (np.asarray([0]), np.asarray([np.nan]), "non-finite"),
        (np.asarray([0]), np.asarray([float(2**63)]), "signed-int64 count domain"),
    ],
)
def test_sparse_block_rejects_noncanonical_or_noncount_values(indices, data, match) -> None:
    with pytest.raises(ValueError, match=match):
        SparseCountBlock(
            row_start=0,
            donor_keys=("d",),
            study_keys=("s",),
            source_labels=("L",),
            indptr=np.asarray([0, len(indices)], dtype=np.int64),
            indices=indices,
            data=data,
        )


def test_crosswalks_are_complete_and_grouped_study_conflicts_fail_closed() -> None:
    incomplete = _donor_crosswalk().model_copy(update={"rules": _donor_crosswalk().rules[:-1]})
    incomplete_recipe = _recipe().model_copy(
        update={"reviewed_donor_crosswalk_digest": incomplete.crosswalk_digest}
    )
    with pytest.raises(GbmapExtractionError, match="donor crosswalk"):
        aggregate_sparse_count_blocks(
            blocks=_blocks(),
            feature_ids=FEATURES,
            gene_symbols=GENE_SYMBOLS,
            source_sha256=DIGEST_A,
            source_bytes=123,
            taxonomy=_taxonomy(),
            donor_crosswalk=incomplete,
            study_crosswalk=_study_crosswalk(),
            recipe=incomplete_recipe,
        )

    conflicting_studies = GbmapStudyCrosswalk(
        crosswalk_id="conflict/1.0.0",
        rules=tuple(
            GbmapStudyCrosswalkRule(
                source_study_category=rule.source_study_category,
                grouped_study_key=(
                    "other-study" if rule.source_study_category == "sB2" else rule.grouped_study_key
                ),
            )
            for rule in _study_crosswalk().rules
        ),
    )
    with pytest.raises(GbmapExtractionError, match="multiple studies"):
        aggregate_sparse_count_blocks(
            blocks=_blocks(),
            feature_ids=FEATURES,
            gene_symbols=GENE_SYMBOLS,
            source_sha256=DIGEST_A,
            source_bytes=123,
            taxonomy=_taxonomy(),
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=conflicting_studies,
            recipe=_recipe().model_copy(
                update={"reviewed_study_crosswalk_digest": conflicting_studies.crosswalk_digest}
            ),
        )


def test_receipt_is_deidentified_and_digest_guarded() -> None:
    receipt = _aggregate().receipt
    serialized = receipt.model_dump_json()
    parsed = json.loads(serialized)
    string_values = {value for value in parsed.values() if isinstance(value, str)}

    for forbidden in (*set(DONORS), "study-a", "lineage-1"):
        assert forbidden not in string_values
    assert "aggregate_content_digest" not in parsed
    assert parsed["donor_identifiers_retained"] is False
    forged = receipt.model_dump(mode="python")
    forged["record_count"] += 1
    with pytest.raises(ValidationError, match="receipt digest"):
        GbmapExtractionReceipt.model_validate(forged, strict=True)


def test_cancellation_is_checked_before_sparse_aggregation() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        aggregate_sparse_count_blocks(
            blocks=_blocks(),
            feature_ids=FEATURES,
            gene_symbols=GENE_SYMBOLS,
            source_sha256=DIGEST_A,
            source_bytes=123,
            taxonomy=_taxonomy(),
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=_study_crosswalk(),
            recipe=_recipe(),
            cancellation=cancellation,
        )


def test_legacy_h5ad_is_extracted_through_exact_two_pass_lock(tmp_path: Path) -> None:
    source = tmp_path / "tiny.h5ad"
    _write_legacy_fixture(source)
    lock = _lock_for(source)

    result = extract_pinned_gbmap_reference(
        source,
        lock=lock,
        taxonomy=_taxonomy(),
        donor_crosswalk=_donor_crosswalk(),
        study_crosswalk=_study_crosswalk(),
        recipe=_recipe(),
    )

    assert _record_projection(result) == _record_projection(_aggregate())
    assert result.receipt.source_sha256 == lock.sha256
    assert result.receipt.source_bytes == lock.expected_bytes


def test_h5ad_wrong_byte_lock_and_wrong_declared_vocabulary_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "tiny.h5ad"
    _write_legacy_fixture(source)
    lock = _lock_for(source)
    wrong_lock = lock.model_copy(update={"sha256": DIGEST_A})
    with pytest.raises(GbmapSourceAdmissionError, match="reviewed lock"):
        extract_pinned_gbmap_reference(
            source,
            lock=wrong_lock,
            taxonomy=_taxonomy(),
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=_study_crosswalk(),
            recipe=_recipe(),
        )

    incomplete_taxonomy = GbmapLabelTaxonomy(
        taxonomy_id="incomplete/1.0.0",
        rules=_taxonomy().rules[:-1],
    )
    incomplete_recipe = _recipe().model_copy(
        update={"reviewed_label_taxonomy_digest": incomplete_taxonomy.taxonomy_digest}
    )
    with pytest.raises(GbmapExtractionError, match="vocabulary"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=incomplete_taxonomy,
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=_study_crosswalk(),
            recipe=incomplete_recipe,
        )


def test_h5ad_fractional_count_is_rejected_without_rounding(tmp_path: Path) -> None:
    source = tmp_path / "fractional.h5ad"
    _write_legacy_fixture(source)
    h5py = pytest.importorskip("h5py")
    with h5py.File(source, "r+") as handle:
        handle["layers/counts/data"][0] = np.float32(1.5)
    lock = _lock_for(source)

    with pytest.raises(GbmapExtractionError, match="fractional count"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=_taxonomy(),
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=_study_crosswalk(),
            recipe=_recipe(),
        )


def test_source_dependency_and_production_layout_are_version_bound() -> None:
    h5py = importlib.import_module("h5py")
    recipe = production_extraction_recipe()
    profile = development_profile()
    donor_crosswalk = production_donor_crosswalk()

    assert h5py.__version__ == EXPECTED_H5PY_VERSION
    assert recipe.matrix_path == "layers/counts"
    assert recipe.expected_cell_count == 338_564
    assert recipe.expected_feature_count == 5_000
    assert recipe.expected_nnz == 196_660_428
    assert recipe.expected_source_donor_category_count == 113
    assert recipe.expected_grouped_donor_category_count == 110
    assert recipe.reviewed_donor_crosswalk_digest == donor_crosswalk.crosswalk_digest
    assert len(donor_crosswalk.rules) == 113
    assert len(donor_crosswalk.grouped_donor_keys) == 110
    assert donor_crosswalk.source_categories == frozenset(PRODUCTION_SOURCE_DONOR_CATEGORIES)
    assert (
        donor_category_set_digest(tuple(donor_crosswalk.grouped_donor_keys))
        == EXPECTED_DONOR_CATEGORY_SET_DIGEST
    )
    assert donor_crosswalk.resolve("PW032-701") == "PW032"
    assert donor_crosswalk.resolve("PW032-702") == "PW032"
    assert donor_crosswalk.resolve("PW032-712") == "PW032"
    assert donor_crosswalk.resolve("R4 n.c.") == "R4"
    assert donor_crosswalk.resolve("R4") == "R4"
    assert recipe.expected_source_study_category_count == 17
    assert recipe.expected_grouped_study_count == 16
    assert recipe.feature_identity_semantics == "source_feature_key_not_stable_gene_id"
    assert len(production_label_taxonomy().rules) == 20
    assert len(production_study_crosswalk().rules) == 17
    assert len(production_study_crosswalk().grouped_study_keys) == 16
    assert profile.source.zenodo_raw_patient_category_count == 113
    assert profile.source.complete_donor_crosswalk_available
    assert not profile.source.raw_patient_categories_may_be_treated_as_independent_donors
    assert profile.source_admission_state == "admitted_private_offline_development_only"


def test_production_recipe_rejects_a_caller_invented_donor_crosswalk() -> None:
    recipe = production_extraction_recipe()

    with pytest.raises(GbmapSourceAdmissionError, match="donor crosswalk differs"):
        aggregate_sparse_count_blocks(
            blocks=(),
            feature_ids=("placeholder",) * recipe.expected_feature_count,
            gene_symbols=(None,) * recipe.expected_feature_count,
            source_sha256=DIGEST_A,
            source_bytes=recipe.expected_cell_count,
            taxonomy=production_label_taxonomy(),
            donor_crosswalk=_donor_crosswalk(),
            study_crosswalk=production_study_crosswalk(),
            recipe=recipe,
        )
