from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution import extraction
from glio_proteogen.research.gbmap_deconvolution.aggregate import AggregateReference
from glio_proteogen.research.gbmap_deconvolution.errors import (
    GbmapExtractionError,
    GbmapSourceAdmissionError,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import (
    ExactGbmapH5adLock,
    GbmapDonorCrosswalk,
    GbmapDonorCrosswalkRule,
    GbmapExtractionReceipt,
    GbmapExtractionRecipe,
    GbmapExtractionResult,
    GbmapLabelTaxonomy,
    GbmapStudyCrosswalk,
    GbmapStudyCrosswalkRule,
    GbmapTaxonomyRule,
    SourceFingerprint,
    SparseCountBlock,
    aggregate_sparse_count_blocks,
    extract_pinned_gbmap_reference,
    fingerprint_gbmap_source,
    production_extraction_recipe,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)
from tests.research import test_gbmap_h5ad_extraction as base

DIGEST_B = "sha256:" + "b" * 64


def _recipe_payload(**updates: object) -> dict[str, object]:
    payload = base._recipe().model_dump(mode="python")
    payload.update(updates)
    return payload


def _extract_fixture(
    source: Path,
    *,
    recipe: GbmapExtractionRecipe | None = None,
    taxonomy: GbmapLabelTaxonomy | None = None,
    donor_crosswalk: GbmapDonorCrosswalk | None = None,
    study_crosswalk: GbmapStudyCrosswalk | None = None,
) -> GbmapExtractionResult:
    return extract_pinned_gbmap_reference(
        source,
        lock=base._lock_for(source),
        taxonomy=taxonomy or base._taxonomy(),
        donor_crosswalk=donor_crosswalk or base._donor_crosswalk(),
        study_crosswalk=study_crosswalk or base._study_crosswalk(),
        recipe=recipe or base._recipe(),
    )


def _aggregate_with(  # noqa: PLR0913
    *,
    blocks: object = None,
    feature_ids: object = None,
    gene_symbols: object = None,
    taxonomy: GbmapLabelTaxonomy | None = None,
    donor_crosswalk: GbmapDonorCrosswalk | None = None,
    study_crosswalk: GbmapStudyCrosswalk | None = None,
    recipe: GbmapExtractionRecipe | None = None,
) -> GbmapExtractionResult:
    return aggregate_sparse_count_blocks(
        blocks=base._blocks() if blocks is None else blocks,  # type: ignore[arg-type]
        feature_ids=base.FEATURES if feature_ids is None else feature_ids,  # type: ignore[arg-type]
        gene_symbols=base.GENE_SYMBOLS if gene_symbols is None else gene_symbols,  # type: ignore[arg-type]
        source_sha256=base.DIGEST_A,
        source_bytes=123,
        taxonomy=taxonomy or base._taxonomy(),
        donor_crosswalk=donor_crosswalk or base._donor_crosswalk(),
        study_crosswalk=study_crosswalk or base._study_crosswalk(),
        recipe=recipe or base._recipe(),
    )


def _replace_dataset(group: Any, name: str, values: object, **kwargs: object) -> Any:
    if name in group:
        del group[name]
    return group.create_dataset(name, data=values, **kwargs)


def _receipt_with(receipt: GbmapExtractionReceipt, **updates: object) -> GbmapExtractionReceipt:
    payload = receipt.model_dump(mode="python", exclude={"receipt_digest"})
    payload.update(updates)
    return GbmapExtractionReceipt.model_validate(
        {"receipt_digest": sha256_digest(payload), **payload},
        strict=True,
    )


@pytest.mark.parametrize(
    "rule",
    [
        {"source_label": "L"},
        {"source_label": "L", "modeled_label": "M", "exclusion_reason": "excluded"},
    ],
)
def test_taxonomy_rule_requires_exactly_one_disposition(rule) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GbmapTaxonomyRule.model_validate(rule)


@pytest.mark.parametrize("bad_text", ["", " padded", "padded ", "x" * 257])
def test_canonical_metadata_text_is_rejected(bad_text: str) -> None:
    with pytest.raises(ValidationError):
        GbmapTaxonomyRule(source_label=bad_text, modeled_label="M")


def test_taxonomy_and_crosswalk_duplicate_sources_are_rejected() -> None:
    duplicate_taxonomy = (
        GbmapTaxonomyRule(source_label="L", modeled_label="M1"),
        GbmapTaxonomyRule(source_label="L", modeled_label="M2"),
    )
    with pytest.raises(ValidationError, match="source labels must be unique"):
        GbmapLabelTaxonomy(taxonomy_id="t/1", rules=duplicate_taxonomy)

    duplicate_donors = (
        GbmapDonorCrosswalkRule(source_donor_category="d", grouped_donor_key="g1"),
        GbmapDonorCrosswalkRule(source_donor_category="d", grouped_donor_key="g2"),
    )
    with pytest.raises(ValidationError, match="source categories must be unique"):
        GbmapDonorCrosswalk(crosswalk_id="d/1", rules=duplicate_donors)

    duplicate_studies = (
        GbmapStudyCrosswalkRule(source_study_category="s", grouped_study_key="g1"),
        GbmapStudyCrosswalkRule(source_study_category="s", grouped_study_key="g2"),
    )
    with pytest.raises(ValidationError, match="source categories must be unique"):
        GbmapStudyCrosswalk(crosswalk_id="s/1", rules=duplicate_studies)


def test_taxonomy_and_crosswalk_resolvers_fail_closed_on_unknown_values() -> None:
    with pytest.raises(GbmapExtractionError, match="absent from the reviewed taxonomy"):
        base._taxonomy().resolve("unknown")
    with pytest.raises(GbmapExtractionError, match="absent from the reviewed donor"):
        base._donor_crosswalk().resolve("unknown")
    with pytest.raises(GbmapExtractionError, match="absent from the reviewed study"):
        base._study_crosswalk().resolve("unknown")


@pytest.mark.parametrize(
    "updates",
    [
        {"matrix_path": "/layers/counts"},
        {"matrix_path": "layers//counts"},
        {"matrix_path": "layers/counts/"},
        {"donor_path": "layers/counts"},
        {"gene_symbol_path": "var/_index"},
        {"donor_categories_path": "obs/__categories/author"},
        {"donor_categories_path": "obs/patient"},
    ],
)
def test_recipe_paths_must_be_canonical_and_distinct(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match=r"path|distinct|unique"):
        GbmapExtractionRecipe.model_validate(_recipe_payload(**updates))


def _valid_sparse_kwargs() -> dict[str, object]:
    return {
        "row_start": 0,
        "donor_keys": ("d",),
        "study_keys": ("s",),
        "source_labels": ("L",),
        "indptr": np.asarray([0, 1], dtype=np.int64),
        "indices": np.asarray([0], dtype=np.int64),
        "data": np.asarray([1], dtype=np.int64),
    }


@pytest.mark.parametrize(
    ("updates", "match"),
    [
        ({"row_start": True}, "row_start"),
        ({"row_start": -1}, "row_start"),
        ({"donor_keys": ["d"]}, "donor_keys"),
        ({"donor_keys": ()}, "donor_keys"),
        ({"study_keys": ["s"]}, "study_keys"),
        ({"study_keys": ()}, "study_keys"),
        ({"source_labels": ["L"]}, "source_labels"),
        ({"source_labels": ()}, "source_labels"),
        ({"donor_keys": (" d",)}, "unpadded"),
        ({"indptr": [0, 1]}, "exact NumPy"),
        ({"indptr": np.asarray([[0, 1]])}, "one-dimensional integer"),
        ({"indptr": np.asarray([False, True])}, "one-dimensional integer"),
        ({"indptr": np.asarray([0, -1])}, "cannot be negative"),
        (
            {"indptr": np.asarray([0, np.iinfo(np.uint64).max], dtype=np.uint64)},
            "exceeds signed int64",
        ),
        ({"data": [1]}, "exact NumPy"),
        ({"data": np.asarray([[1]])}, "numeric one-dimensional"),
        ({"data": np.asarray([True])}, "numeric one-dimensional"),
        ({"data": np.asarray([np.inf])}, "non-finite"),
        ({"data": np.asarray([-1.0])}, "signed-int64 count domain"),
        (
            {"data": np.asarray([np.nextafter(float(np.iinfo(np.int64).max), np.inf)])},
            "signed-int64",
        ),
        (
            {"data": np.asarray([np.iinfo(np.uint64).max], dtype=np.uint64)},
            "exceeds signed int64",
        ),
        ({"indptr": np.asarray([1, 1])}, "start at zero"),
        ({"indptr": np.asarray([0, 1, 1])}, "one pointer per row"),
        ({"indptr": np.asarray([0, 2]), "indices": np.asarray([0])}, "lengths do not reconcile"),
    ],
)
def test_sparse_block_rejects_malformed_types_metadata_and_csr(
    updates: dict[str, object], match: str
) -> None:
    kwargs = _valid_sparse_kwargs()
    kwargs.update(updates)
    with pytest.raises(ValueError, match=match):
        SparseCountBlock(**kwargs)  # type: ignore[arg-type]


def test_sparse_block_rejects_nonmonotone_pointer_and_freezes_arrays() -> None:
    kwargs = _valid_sparse_kwargs()
    kwargs.update(
        donor_keys=("d1", "d2"),
        study_keys=("s", "s"),
        source_labels=("L", "L"),
        indptr=np.asarray([0, 1, 0]),
    )
    with pytest.raises(ValueError, match="monotone"):
        SparseCountBlock(**kwargs)  # type: ignore[arg-type]

    block = SparseCountBlock(**_valid_sparse_kwargs())  # type: ignore[arg-type]
    assert not block.indptr.flags.writeable
    assert not block.indices.flags.writeable
    assert not block.data.flags.writeable


@pytest.mark.parametrize(
    ("updates", "match"),
    [
        ({"reviewed_donor_crosswalk_digest": None}, "unresolved and not admitted"),
        ({"reviewed_donor_crosswalk_digest": DIGEST_B}, "donor crosswalk"),
        ({"reviewed_study_crosswalk_digest": DIGEST_B}, "study crosswalk"),
        ({"reviewed_label_taxonomy_digest": DIGEST_B}, "label taxonomy"),
    ],
)
def test_aggregation_requires_each_reviewed_semantic_digest(
    updates: dict[str, object], match: str
) -> None:
    with pytest.raises(GbmapSourceAdmissionError, match=match):
        _aggregate_with(recipe=base._recipe().model_copy(update=updates))


@pytest.mark.parametrize(
    ("feature_ids", "gene_symbols", "match"),
    [
        (("G1", "G2"), (None, None), "feature count"),
        (base.FEATURES, (None,), "align"),
        (("G1", "G1", "G3"), base.GENE_SYMBOLS, "unique"),
        ((" G1", "G2", "G3"), base.GENE_SYMBOLS, "unpadded"),
        (base.FEATURES, (None, " B", None), "unpadded"),
    ],
)
def test_aggregation_rejects_invalid_feature_metadata(
    feature_ids: tuple[str, ...], gene_symbols: tuple[str | None, ...], match: str
) -> None:
    with pytest.raises((GbmapExtractionError, ValueError), match=match):
        _aggregate_with(feature_ids=feature_ids, gene_symbols=gene_symbols)


def test_aggregation_requires_exact_contiguous_bounded_blocks() -> None:
    with pytest.raises(GbmapExtractionError, match="at least one"):
        _aggregate_with(blocks=())
    with pytest.raises(GbmapExtractionError, match="exact SparseCountBlock"):
        _aggregate_with(blocks=(object(),))

    displaced = replace(base._blocks()[0], row_start=1)
    with pytest.raises(GbmapExtractionError, match="contiguously"):
        _aggregate_with(blocks=(displaced, *base._blocks()[1:]))

    out_of_bounds = replace(
        base._blocks()[0],
        indices=np.asarray([0, 3, 1], dtype=np.int64),
    )
    with pytest.raises(GbmapExtractionError, match="feature boundary"):
        _aggregate_with(blocks=(out_of_bounds, *base._blocks()[1:]))


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("expected_cell_count", 6, "cell count"),
        ("expected_source_donor_category_count", 5, "patient-category count"),
        ("expected_grouped_donor_category_count", 4, "grouped donor-category count"),
        ("expected_source_study_category_count", 5, "author-category count"),
        ("expected_grouped_study_count", 4, "grouped study count"),
        ("expected_source_label_count", 4, "source label count"),
    ],
)
def test_aggregation_enforces_dimensional_closure(field: str, value: int, match: str) -> None:
    recipe = base._recipe().model_copy(update={field: value})
    with pytest.raises(GbmapExtractionError, match=match):
        _aggregate_with(recipe=recipe)


def test_aggregation_requires_exact_taxonomy_and_crosswalk_vocabularies() -> None:
    taxonomy = GbmapLabelTaxonomy(
        taxonomy_id="extra/1",
        rules=(
            *base._taxonomy().rules,
            GbmapTaxonomyRule(source_label="unused", modeled_label="U"),
        ),
    )
    with pytest.raises(GbmapExtractionError, match=r"Taxonomy|taxonomy"):
        _aggregate_with(
            taxonomy=taxonomy,
            recipe=base._recipe().model_copy(
                update={"reviewed_label_taxonomy_digest": taxonomy.taxonomy_digest}
            ),
        )

    donor_crosswalk = GbmapDonorCrosswalk(
        crosswalk_id="extra-donor/1",
        rules=(
            *base._donor_crosswalk().rules,
            GbmapDonorCrosswalkRule(source_donor_category="unused", grouped_donor_key="d1"),
        ),
    )
    with pytest.raises(GbmapExtractionError, match=r"exactly cover.*patient"):
        _aggregate_with(
            donor_crosswalk=donor_crosswalk,
            recipe=base._recipe().model_copy(
                update={"reviewed_donor_crosswalk_digest": donor_crosswalk.crosswalk_digest}
            ),
        )

    study_crosswalk = GbmapStudyCrosswalk(
        crosswalk_id="extra-study/1",
        rules=(
            *base._study_crosswalk().rules,
            GbmapStudyCrosswalkRule(source_study_category="unused", grouped_study_key="study-a"),
        ),
    )
    with pytest.raises(GbmapExtractionError, match=r"exactly cover.*author"):
        _aggregate_with(
            study_crosswalk=study_crosswalk,
            recipe=base._recipe().model_copy(
                update={"reviewed_study_crosswalk_digest": study_crosswalk.crosswalk_digest}
            ),
        )


def test_aggregation_grouped_key_and_donor_set_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        GbmapDonorCrosswalk,
        "grouped_donor_keys",
        property(lambda self: frozenset({"d1", "d2", "d3", "unused"})),
    )
    with pytest.raises(GbmapExtractionError, match="grouped-key closure"):
        _aggregate_with()

    monkeypatch.undo()
    monkeypatch.setattr(
        GbmapStudyCrosswalk,
        "grouped_study_keys",
        property(lambda self: frozenset({"study-a", "study-b", "study-c", "unused"})),
    )
    with pytest.raises(GbmapExtractionError, match="grouped-key closure"):
        _aggregate_with()

    monkeypatch.undo()
    with pytest.raises(GbmapExtractionError, match="pinned set"):
        _aggregate_with(
            recipe=base._recipe().model_copy(
                update={"expected_grouped_donor_category_set_digest": DIGEST_B}
            )
        )


def test_aggregation_rejects_a_taxonomy_that_excludes_every_cell() -> None:
    taxonomy = GbmapLabelTaxonomy(
        taxonomy_id="exclude-all/1",
        rules=tuple(
            GbmapTaxonomyRule(source_label=label, exclusion_reason="not modeled")
            for label in ("L1", "L2", "EX")
        ),
    )
    recipe = base._recipe().model_copy(
        update={"reviewed_label_taxonomy_digest": taxonomy.taxonomy_digest}
    )
    with pytest.raises(GbmapExtractionError, match="excluded every"):
        _aggregate_with(taxonomy=taxonomy, recipe=recipe)


def _private_builder() -> extraction._AggregateBuilder:
    return extraction._AggregateBuilder(
        feature_ids=base.FEATURES,
        gene_symbols=base.GENE_SYMBOLS,
        source_sha256=base.DIGEST_A,
        source_bytes=123,
        taxonomy=base._taxonomy(),
        donor_crosswalk=base._donor_crosswalk(),
        study_crosswalk=base._study_crosswalk(),
        recipe=base._recipe(),
        cancellation=None,
    )


def _single_row_block(*, row_start: int, column: int, count: int) -> SparseCountBlock:
    return SparseCountBlock(
        row_start=row_start,
        donor_keys=("d1a",),
        study_keys=("sA",),
        source_labels=("L1",),
        indptr=np.asarray([0, 1], dtype=np.int64),
        indices=np.asarray([column], dtype=np.int64),
        data=np.asarray([count], dtype=np.int64),
    )


def test_private_builder_rejects_aggregate_study_assignment_drift() -> None:
    builder = _private_builder()
    builder.ingest(_single_row_block(row_start=0, column=0, count=1))
    builder._aggregates[("d1", "lineage-1")].study_key = "forged-study"
    with pytest.raises(GbmapExtractionError, match="assignment drifted"):
        builder.ingest(_single_row_block(row_start=1, column=1, count=1))


def test_private_builder_checked_integer_accumulation(monkeypatch: pytest.MonkeyPatch) -> None:
    gene_builder = _private_builder()
    gene_builder.ingest(_single_row_block(row_start=0, column=0, count=np.iinfo(np.int64).max))
    with pytest.raises(GbmapExtractionError, match="gene-count accumulation"):
        gene_builder.ingest(_single_row_block(row_start=1, column=0, count=1))

    umi_builder = _private_builder()
    umi_builder.ingest(_single_row_block(row_start=0, column=0, count=np.iinfo(np.int64).max))
    with pytest.raises(GbmapExtractionError, match="UMI accumulation"):
        umi_builder.ingest(_single_row_block(row_start=1, column=1, count=1))

    monkeypatch.setattr(extraction, "_INT32_MAX", 0)
    with pytest.raises(GbmapExtractionError, match="detection-count accumulation"):
        _private_builder().ingest(_single_row_block(row_start=0, column=0, count=1))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha256", DIGEST_B),
        ("source_bytes", 124),
        ("taxonomy_digest", DIGEST_B),
        ("extraction_recipe_digest", DIGEST_B),
        ("feature_order_digest", DIGEST_B),
    ],
)
def test_extraction_result_reconciles_every_reference_binding(field: str, value: object) -> None:
    result = base._aggregate()
    receipt = _receipt_with(result.receipt, **{field: value})
    with pytest.raises(ValueError, match="disagree"):
        GbmapExtractionResult(reference=result.reference, receipt=receipt)


def test_extraction_result_requires_exact_component_types() -> None:
    result = base._aggregate()
    with pytest.raises(ValueError, match="exact AggregateReference"):
        GbmapExtractionResult(reference=object(), receipt=result.receipt)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact GbmapExtractionReceipt"):
        GbmapExtractionResult(reference=result.reference, receipt=object())  # type: ignore[arg-type]
    assert isinstance(result.reference, AggregateReference)


def _write_direct_fixture(path: Path, *, modern_categories: bool, gene_symbols: bool) -> None:
    h5py = pytest.importorskip("h5py")
    text_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as handle:
        counts = handle.create_group("layers").create_group("counts")
        counts.attrs["encoding-type"] = "csr_matrix"
        counts.attrs["encoding-version"] = "0.1.0"
        counts.attrs["shape"] = np.asarray([5, 3], dtype=np.int64)
        counts.create_dataset("data", data=base.COUNTS.astype(np.float32))
        counts.create_dataset("indices", data=base.INDICES.astype(np.int32))
        counts.create_dataset("indptr", data=base.INDPTR.astype(np.int32))
        var = handle.create_group("var")
        var.create_dataset("_index", data=np.asarray(base.FEATURES, dtype=text_dtype))
        if gene_symbols:
            var.create_dataset(
                "symbols", data=np.asarray(("Gene 1", "Gene 2", "Gene 3"), dtype=text_dtype)
            )
        obs = handle.create_group("obs")
        for name, values in (
            ("patient", base.DONORS),
            ("author", base.STUDIES),
            ("CellID", base.LABELS),
        ):
            if modern_categories:
                vocabulary = tuple(dict.fromkeys(values))
                lookup = {value: index for index, value in enumerate(vocabulary)}
                categorical = obs.create_group(name)
                categorical.create_dataset(
                    "codes", data=np.asarray([lookup[value] for value in values], dtype=np.int8)
                )
                categorical.create_dataset(
                    "categories", data=np.asarray(vocabulary, dtype=text_dtype)
                )
            else:
                obs.create_dataset(name, data=np.asarray(values, dtype=text_dtype))


def _mutate_csr_fixture(  # noqa: C901, PLR0912, PLR0915
    source: Path, case: str
) -> GbmapExtractionRecipe:
    h5py = pytest.importorskip("h5py")
    recipe = base._recipe()
    with h5py.File(source, "r+") as handle:
        counts = handle["layers/counts"]
        if case == "matrix_dataset":
            del handle["layers/counts"]
            handle["layers"].create_dataset("counts", data=np.asarray([1], dtype=np.int8))
        elif case == "encoding_type":
            counts.attrs["encoding-type"] = "csc_matrix"
        elif case == "encoding_version":
            counts.attrs["encoding-version"] = "0.2.0"
        elif case == "shape_rank":
            counts.attrs["shape"] = np.asarray([5], dtype=np.int64)
        elif case == "shape_bool":
            counts.attrs["shape"] = np.asarray([True, True])
        elif case == "shape_nonpositive":
            counts.attrs["shape"] = np.asarray([0, 3], dtype=np.int64)
        elif case == "shape_mismatch":
            counts.attrs["shape"] = np.asarray([4, 3], dtype=np.int64)
        elif case == "missing_data":
            del counts["data"]
        elif case == "data_rank":
            _replace_dataset(counts, "data", base.COUNTS.reshape(2, 3).astype(np.float32))
        elif case == "indices_rank":
            _replace_dataset(counts, "indices", base.INDICES.reshape(2, 3).astype(np.int32))
        elif case == "indptr_shape":
            _replace_dataset(counts, "indptr", base.INDPTR[:-1].astype(np.int32))
        elif case == "length_mismatch":
            _replace_dataset(counts, "indices", base.INDICES[:-1].astype(np.int32))
        elif case == "nnz_mismatch":
            recipe = recipe.model_copy(update={"expected_nnz": 7})
        elif case == "data_dtype":
            _replace_dataset(counts, "data", base.COUNTS.astype(np.float64))
        elif case == "indices_dtype":
            _replace_dataset(counts, "indices", base.INDICES.astype(np.int64))
        elif case == "indptr_dtype":
            _replace_dataset(counts, "indptr", base.INDPTR.astype(np.int64))
        elif case == "indptr_start":
            values = base.INDPTR.astype(np.int32).copy()
            values[0] = 1
            _replace_dataset(counts, "indptr", values)
        elif case == "indptr_decreasing":
            values = base.INDPTR.astype(np.int32).copy()
            values[2] = 1
            _replace_dataset(counts, "indptr", values)
        elif case == "indptr_does_not_close":
            values = base.INDPTR.astype(np.int32).copy()
            values[-1] = 5
            _replace_dataset(counts, "indptr", values)
        elif case == "column_out_of_bounds":
            values = base.INDICES.astype(np.int32).copy()
            values[1] = 3
            _replace_dataset(counts, "indices", values)
        elif case == "duplicate_column":
            values = base.INDICES.astype(np.int32).copy()
            values[1] = values[0]
            _replace_dataset(counts, "indices", values)
        elif case == "explicit_zero":
            values = base.COUNTS.astype(np.float32).copy()
            values[0] = 0.0
            _replace_dataset(counts, "data", values)
        elif case == "negative_count":
            values = base.COUNTS.astype(np.float32).copy()
            values[0] = -1.0
            _replace_dataset(counts, "data", values)
        elif case == "nonfinite_count":
            values = base.COUNTS.astype(np.float32).copy()
            values[0] = np.inf
            _replace_dataset(counts, "data", values)
        elif case == "missing_feature":
            del handle["var/_index"]
        elif case == "feature_shape":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            _replace_dataset(handle["var"], "_index", np.asarray(("G1", "G2"), dtype=text_dtype))
        elif case == "feature_duplicate":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            _replace_dataset(
                handle["var"], "_index", np.asarray(("G1", "G1", "G3"), dtype=text_dtype)
            )
        elif case == "feature_invalid_utf8":
            _replace_dataset(handle["var"], "_index", np.asarray([b"G1", b"\xff", b"G3"]))
        else:  # pragma: no cover - test table is closed below
            raise AssertionError(case)
    return recipe


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("matrix_dataset", "locked CSR encoding"),
        ("encoding_type", "locked CSR encoding"),
        ("encoding_version", "locked CSR encoding"),
        ("shape_rank", "shape attribute is invalid"),
        ("shape_bool", "shape attribute is invalid"),
        ("shape_nonpositive", "shape must be positive"),
        ("shape_mismatch", "shape differs"),
        ("missing_data", "CSR layer is incomplete"),
        ("data_rank", "data and indices must be vectors"),
        ("indices_rank", "data and indices must be vectors"),
        ("indptr_shape", "indptr has the wrong shape"),
        ("length_mismatch", "data and index lengths disagree"),
        ("nnz_mismatch", "stored-entry count differs"),
        ("data_dtype", "count data dtype differs"),
        ("indices_dtype", "column-index dtype differs"),
        ("indptr_dtype", "row-pointer dtype differs"),
        ("indptr_start", "indptr is not canonical"),
        ("indptr_decreasing", "indptr is not canonical"),
        ("indptr_does_not_close", "does not close"),
        ("column_out_of_bounds", "feature boundary"),
        ("duplicate_column", "strictly increasing"),
        ("explicit_zero", "explicit sparse zero"),
        ("negative_count", "signed-int64 count domain"),
        ("nonfinite_count", "non-finite"),
        ("missing_feature", "missing a required object"),
        ("feature_shape", "wrong shape"),
        ("feature_duplicate", "must be unique"),
        ("feature_invalid_utf8", "not valid UTF-8"),
    ],
)
def test_h5_csr_and_feature_malformations_fail_closed(
    tmp_path: Path, case: str, match: str
) -> None:
    source = tmp_path / f"{case}.h5ad"
    base._write_legacy_fixture(source)
    recipe = _mutate_csr_fixture(source, case)
    with pytest.raises(GbmapExtractionError, match=match):
        _extract_fixture(source, recipe=recipe)


def _mutate_legacy_category(  # noqa: C901, PLR0912
    source: Path, case: str
) -> None:
    h5py = pytest.importorskip("h5py")
    with h5py.File(source, "r+") as handle:
        obs = handle["obs"]
        categories = obs["__categories"]
        codes = obs["patient"]
        category_dataset = categories["patient"]
        if case == "codes_group":
            del obs["patient"]
            obs.create_group("patient")
        elif case == "codes_shape":
            replacement = _replace_dataset(obs, "patient", np.asarray([0, 1], dtype=np.int8))
            replacement.attrs["categories"] = category_dataset.ref
        elif case == "categories_rank":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            replacement = _replace_dataset(
                categories,
                "patient",
                np.asarray([["d1a", "d1b"], ["d2", "d3"]], dtype=text_dtype),
            )
            codes.attrs["categories"] = replacement.ref
        elif case == "categories_duplicate":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            replacement = _replace_dataset(
                categories,
                "patient",
                np.asarray(("d1a", "d1a", "d2", "d3"), dtype=text_dtype),
            )
            codes.attrs["categories"] = replacement.ref
        elif case == "categories_empty":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            replacement = _replace_dataset(categories, "patient", np.asarray((), dtype=text_dtype))
            codes.attrs["categories"] = replacement.ref
        elif case == "missing_reference":
            del codes.attrs["categories"]
        elif case == "invalid_reference":
            codes.attrs["categories"] = h5py.Reference()
        elif case == "wrong_reference":
            codes.attrs["categories"] = categories["author"].ref
        elif case == "ordered":
            category_dataset.attrs["ordered"] = True
        elif case == "codes_float":
            replacement = _replace_dataset(
                obs, "patient", np.asarray([0, 1, 2, 2, 3], dtype=np.float32)
            )
            replacement.attrs["categories"] = category_dataset.ref
        elif case == "code_negative":
            codes[0] = -1
        elif case == "code_high":
            codes[0] = 99
        elif case == "categories_invalid_utf8":
            replacement = _replace_dataset(
                categories, "patient", np.asarray([b"d1a", b"d1b", b"d2", b"\xff"])
            )
            replacement.attrs["ordered"] = False
            codes.attrs["categories"] = replacement.ref
        else:  # pragma: no cover - test table is closed below
            raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("codes_group", "legacy categorical codes have the wrong shape"),
        ("codes_shape", "legacy categorical codes have the wrong shape"),
        ("categories_rank", "must be one-dimensional"),
        ("categories_duplicate", "nonempty and unique"),
        ("categories_empty", "nonempty and unique"),
        ("missing_reference", "lacks its legacy categories reference"),
        ("invalid_reference", "invalid categories reference"),
        ("wrong_reference", "points elsewhere"),
        ("ordered", "explicitly unordered"),
        ("codes_float", "categorical codes must be integers"),
        ("code_negative", "missing or invalid code"),
        ("code_high", "missing or invalid code"),
        ("categories_invalid_utf8", "not valid UTF-8"),
    ],
)
def test_legacy_categorical_malformations_fail_closed(
    tmp_path: Path, case: str, match: str
) -> None:
    source = tmp_path / f"legacy-{case}.h5ad"
    base._write_legacy_fixture(source)
    _mutate_legacy_category(source, case)
    with pytest.raises(GbmapExtractionError, match=match):
        _extract_fixture(source)


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("incomplete", "categorical encoding is incomplete"),
        ("codes_shape", "categorical codes have the wrong shape"),
        ("categories_duplicate", "nonempty and unique"),
        ("codes_float", "categorical codes must be integers"),
        ("code_high", "missing or invalid code"),
    ],
)
def test_modern_categorical_malformations_fail_closed(
    tmp_path: Path, case: str, match: str
) -> None:
    source = tmp_path / f"modern-{case}.h5ad"
    _write_direct_fixture(source, modern_categories=True, gene_symbols=False)
    h5py = pytest.importorskip("h5py")
    with h5py.File(source, "r+") as handle:
        categorical = handle["obs/patient"]
        if case == "incomplete":
            del categorical["categories"]
        elif case == "codes_shape":
            _replace_dataset(categorical, "codes", np.asarray([0, 1], dtype=np.int8))
        elif case == "categories_duplicate":
            text_dtype = h5py.string_dtype(encoding="utf-8")
            _replace_dataset(
                categorical,
                "categories",
                np.asarray(("d1a", "d1a", "d2", "d3"), dtype=text_dtype),
            )
        elif case == "codes_float":
            _replace_dataset(categorical, "codes", np.asarray([0, 1, 2, 2, 3], dtype=np.float32))
        elif case == "code_high":
            categorical["codes"][0] = 99
    with pytest.raises(GbmapExtractionError, match=match):
        _extract_fixture(source, recipe=base._recipe(legacy=False))


def test_direct_text_and_optional_gene_symbol_paths_are_extracted(tmp_path: Path) -> None:
    source = tmp_path / "direct.h5ad"
    _write_direct_fixture(source, modern_categories=False, gene_symbols=True)
    recipe = base._recipe(legacy=False).model_copy(update={"gene_symbol_path": "var/symbols"})
    result = _extract_fixture(source, recipe=recipe)
    assert result.reference.gene_symbols == ("Gene 1", "Gene 2", "Gene 3")


def test_direct_text_annotation_shape_and_type_fail_closed(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    wrong_shape = tmp_path / "wrong-shape.h5ad"
    _write_direct_fixture(wrong_shape, modern_categories=False, gene_symbols=False)
    with h5py.File(wrong_shape, "r+") as handle:
        text_dtype = h5py.string_dtype(encoding="utf-8")
        _replace_dataset(handle["obs"], "patient", np.asarray(("d1", "d2"), dtype=text_dtype))
    with pytest.raises(GbmapExtractionError, match="wrong shape"):
        _extract_fixture(wrong_shape, recipe=base._recipe(legacy=False))

    non_text = tmp_path / "non-text.h5ad"
    _write_direct_fixture(non_text, modern_categories=False, gene_symbols=False)
    with h5py.File(non_text, "r+") as handle:
        _replace_dataset(handle["obs"], "patient", np.asarray([0, 1, 2, 2, 3]))
    with pytest.raises(GbmapExtractionError, match="must contain UTF-8 text"):
        _extract_fixture(non_text, recipe=base._recipe(legacy=False))


def test_source_fingerprinting_rejects_missing_directory_empty_and_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(GbmapSourceAdmissionError, match="unavailable"):
        fingerprint_gbmap_source(tmp_path / "missing.h5ad")
    with pytest.raises(GbmapSourceAdmissionError, match="regular file"):
        fingerprint_gbmap_source(tmp_path)

    empty = tmp_path / "empty.h5ad"
    empty.touch()
    with pytest.raises(GbmapSourceAdmissionError, match="nonempty"):
        fingerprint_gbmap_source(empty)

    source = tmp_path / "source.h5ad"
    source.write_bytes(b"not-empty")
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == source)
    with pytest.raises(GbmapSourceAdmissionError, match="link or reparse"):
        fingerprint_gbmap_source(source)


def test_hashing_rejects_empty_handles_and_honors_cancellation(tmp_path: Path) -> None:
    with pytest.raises(GbmapSourceAdmissionError, match="nonempty"):
        extraction._hash_open_handle(io.BytesIO(), None)

    source = tmp_path / "cancelled.h5ad"
    source.write_bytes(b"content")
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        fingerprint_gbmap_source(source, cancellation=cancellation)


def _identity_mutator(differing_call: int):
    original = extraction._file_identity
    calls = 0

    def identify(info):
        nonlocal calls
        calls += 1
        identity = original(info)
        if calls == differing_call:
            return (*identity[:-1], identity[-1] + 1)
        return identity

    return identify


@pytest.mark.parametrize(
    ("differing_call", "match"),
    [
        (2, "changed while it was opened"),
        (4, "changed during fingerprinting"),
    ],
)
def test_fingerprinting_detects_identity_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    differing_call: int,
    match: str,
) -> None:
    source = tmp_path / f"race-{differing_call}.h5ad"
    source.write_bytes(b"identity-guard")
    monkeypatch.setattr(extraction, "_file_identity", _identity_mutator(differing_call))
    with pytest.raises(GbmapSourceAdmissionError, match=match):
        fingerprint_gbmap_source(source)


def test_fingerprinting_detects_hash_length_drift_and_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "length.h5ad"
    source.write_bytes(b"length")
    fingerprint = fingerprint_gbmap_source(source)
    monkeypatch.setattr(
        extraction,
        "_hash_open_handle",
        lambda handle, cancellation: fingerprint.model_copy(
            update={"source_bytes": fingerprint.source_bytes + 1}
        ),
    )
    with pytest.raises(GbmapSourceAdmissionError, match="length changed"):
        fingerprint_gbmap_source(source)

    monkeypatch.setattr(
        extraction,
        "_hash_open_handle",
        lambda handle, cancellation: (_ for _ in ()).throw(OSError("read failed")),
    )
    with pytest.raises(GbmapSourceAdmissionError, match="could not be fingerprinted"):
        fingerprint_gbmap_source(source)


def test_open_length_guard_rejects_disagreement(tmp_path: Path) -> None:
    source = tmp_path / "length-guard.h5ad"
    source.write_bytes(b"abc")
    fingerprint = fingerprint_gbmap_source(source).model_copy(update={"source_bytes": 4})
    with source.open("rb") as handle, pytest.raises(GbmapSourceAdmissionError, match="open handle"):
        extraction._require_open_length(fingerprint, extraction.os.fstat(handle.fileno()))


def test_extract_requires_path_and_exact_production_lock(tmp_path: Path) -> None:
    source = tmp_path / "tiny.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)
    with pytest.raises(GbmapSourceAdmissionError, match="pathlib path"):
        extract_pinned_gbmap_reference(  # type: ignore[arg-type]
            str(source),
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )

    with pytest.raises(GbmapSourceAdmissionError, match="Zenodo source lock metadata"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=production_extraction_recipe(),
        )


@pytest.mark.parametrize("reported_version", [None, "3.15.1"])
def test_extract_requires_exact_h5py_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reported_version: str | None
) -> None:
    source = tmp_path / "version.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)
    monkeypatch.setattr(
        extraction.importlib,
        "import_module",
        lambda name: SimpleNamespace(__version__=reported_version),
    )
    with pytest.raises(GbmapSourceAdmissionError, match="version differs"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


def test_extract_reports_missing_offline_h5py_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "missing-dependency.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)

    def missing_dependency(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(extraction.importlib, "import_module", missing_dependency)
    with pytest.raises(GbmapSourceAdmissionError, match="locked source dependency group"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


def test_extract_wraps_open_and_h5_runtime_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "runtime.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)

    def fail_open(_self: Path, *_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(GbmapExtractionError, match="extraction failed closed"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )

    monkeypatch.undo()

    class BrokenFile:
        def __call__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError

    monkeypatch.setattr(
        extraction,
        "_load_h5py",
        lambda recipe: SimpleNamespace(File=BrokenFile()),
    )
    with pytest.raises(GbmapExtractionError, match="extraction failed closed"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


def test_extract_detects_double_hash_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "double-hash.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)
    original_hash = extraction._hash_open_handle
    calls = 0

    def changing_hash(handle, cancellation):
        nonlocal calls
        calls += 1
        fingerprint = original_hash(handle, cancellation)
        if calls == 2:
            return fingerprint.model_copy(update={"sha256": DIGEST_B})
        return fingerprint

    monkeypatch.setattr(extraction, "_hash_open_handle", changing_hash)
    with pytest.raises(GbmapSourceAdmissionError, match="changed during H5AD extraction"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


@pytest.mark.parametrize(
    ("differing_call", "match"),
    [
        (2, "changed while it was opened"),
        (4, "identity changed during"),
        (6, "path changed during"),
    ],
)
def test_extract_detects_handle_and_path_identity_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    differing_call: int,
    match: str,
) -> None:
    source = tmp_path / f"extract-race-{differing_call}.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)
    monkeypatch.setattr(extraction, "_file_identity", _identity_mutator(differing_call))
    with pytest.raises(GbmapSourceAdmissionError, match=match):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


def test_extract_rechecks_final_path_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "final-path.h5ad"
    base._write_legacy_fixture(source)
    lock = base._lock_for(source)
    original = extraction._require_regular_source
    calls = 0

    def path_guard(path: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            return original(path.with_name("missing.h5ad"))
        return original(path)

    monkeypatch.setattr(extraction, "_require_regular_source", path_guard)
    with pytest.raises(GbmapSourceAdmissionError, match="unavailable"):
        extract_pinned_gbmap_reference(
            source,
            lock=lock,
            taxonomy=base._taxonomy(),
            donor_crosswalk=base._donor_crosswalk(),
            study_crosswalk=base._study_crosswalk(),
            recipe=base._recipe(),
        )


def test_text_helpers_and_reader_boundary_guards() -> None:
    with pytest.raises(GbmapExtractionError, match="HDF5 vector"):
        extraction._decode_text_array(["not", "an", "array"], "text")
    with pytest.raises(GbmapExtractionError, match="one-dimensional"):
        extraction._decode_text_array(np.asarray([["nested"]]), "text")

    class Dataset:
        shape = (1,)

        def __getitem__(self, key: object) -> np.ndarray:
            return np.asarray([b"value"])

    reader = extraction._H5TextReader(Dataset(), length=1, name="text")
    with pytest.raises(GbmapExtractionError, match="outside its source boundary"):
        reader.read(-1, 1)
    with pytest.raises(GbmapExtractionError, match="outside its source boundary"):
        reader.read(0, 2)
    reader._dataset = None
    with pytest.raises(GbmapExtractionError, match="not initialized"):
        reader.read(0, 1)


def test_lock_and_fingerprint_models_are_strict_and_nonadmitting() -> None:
    with pytest.raises(ValidationError):
        ExactGbmapH5adLock(
            source_id=" padded",
            expected_bytes=1,
            md5="a" * 32,
            sha256=base.DIGEST_A,
        )
    fingerprint = SourceFingerprint(
        source_bytes=1,
        md5="a" * 32,
        sha256=base.DIGEST_A,
    )
    assert fingerprint.admission_granted is False


def test_remaining_validation_halves_have_explicit_witnesses() -> None:
    with pytest.raises(ValueError, match="exceeds 2 characters"):
        extraction._canonical_text("abc", "tiny", maximum=2)

    empty_unsigned = np.asarray([], dtype=np.uint64)
    assert extraction._exact_index_vector(empty_unsigned, "indices").size == 0
    assert extraction._exact_count_vector(empty_unsigned, "counts").size == 0

    excluded = GbmapLabelTaxonomy(
        taxonomy_id="excluded/1",
        rules=(GbmapTaxonomyRule(source_label="L", exclusion_reason="excluded"),),
    )
    assert excluded.modeled_labels == frozenset()

    receipt = base._aggregate().receipt
    forged = receipt.model_dump(mode="python")
    forged["retained_cell_count"] += 1
    with pytest.raises(ValidationError, match="retained and excluded cells"):
        GbmapExtractionReceipt.model_validate(forged, strict=True)


def test_matching_donor_set_and_production_metadata_locks_are_accepted() -> None:
    donor_digest = extraction.donor_category_set_digest(("d1", "d2", "d3"))
    result = _aggregate_with(
        recipe=base._recipe().model_copy(
            update={"expected_grouped_donor_category_set_digest": donor_digest}
        )
    )
    assert result.receipt.grouped_donor_category_count == 3

    lock = ExactGbmapH5adLock(
        source_id=extraction.ZENODO_SOURCE_ID,
        expected_bytes=extraction.ZENODO_SOURCE_BYTES,
        md5=extraction.ZENODO_SOURCE_MD5,
        sha256=base.DIGEST_A,
    )
    extraction._require_recipe_source_lock(production_extraction_recipe(), lock)
