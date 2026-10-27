"""Independent synthetic stream, empirical-mass and privacy draw oracles."""

from __future__ import annotations

import json
import pickle
from collections import Counter
from dataclasses import FrozenInstanceError, asdict, replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import resampling
from glio_proteogen.research.cptac_gbm_external_admission.resampling import (
    ResamplingError,
    TwoCohortDraw,
    TwoCohortDrawReceipt,
    generate_two_cohort_draws,
)

_DIGEST = "sha256:" + "0123456789abcdef" * 4


def _folds(count=71):
    return np.resize(np.array([4, 2, 0, 3, 1], dtype=np.int8), count)


@pytest.fixture(scope="module")
def schedule():
    return generate_two_cohort_draws(
        source_folds=_folds(), external_count=7, request_digest=_DIGEST
    )


def _manual_draw():
    indices = np.repeat(np.arange(0, 60, 12, dtype=np.int64), 12)
    indices[6::12] += 1
    indices[7::12] += 1
    indices[8::12] += 1
    indices[9::12] += 1
    indices[10::12] += 1
    indices[11::12] += 1
    folds = np.repeat(np.arange(5, dtype=np.int8), 12)
    external = np.array([0, 0, 0, 1], dtype=np.int64)
    receipt = TwoCohortDrawReceipt(
        draw_ordinal=0,
        source_count=60,
        external_count=4,
        source_unique_count=10,
        external_unique_count=2,
        source_fold_counts=(12, 12, 12, 12, 12),
        source_fold_unique_counts=(2, 2, 2, 2, 2),
        source_effective_count=10.0,
        external_effective_count=1.6,
        source_fold_effective_counts=(2.0, 2.0, 2.0, 2.0, 2.0),
    )
    return indices, folds, external, receipt


def test_all128_draws_match_independent_literal_seed_pcg64_integer_oracle(schedule):
    # Literal seeds are independently locked to the documented namespace/digest.
    # Integer positions provide an oracle independent of Generator.choice.
    source_rng = np.random.Generator(np.random.PCG64(5_726_218_801_509_061_901))
    external_rng = np.random.Generator(np.random.PCG64(17_047_138_531_936_287_964))
    original = _folds()
    assert len(schedule) == 128
    for ordinal, draw in enumerate(schedule):
        wanted_source = []
        for label in range(5):
            units = np.flatnonzero(original == label)
            positions = source_rng.integers(0, len(units), size=len(units), dtype=np.int64)
            wanted_source.extend(units[positions])
        wanted_external = external_rng.integers(0, 7, size=7, dtype=np.int64)
        np.testing.assert_array_equal(draw.source_indices, wanted_source)
        np.testing.assert_array_equal(draw.external_indices, wanted_external)
        assert draw.receipt.draw_ordinal == ordinal


def test_all_copies_preserve_original_fold_with_unsorted_original_rows(schedule):
    original = _folds()
    original_counts = tuple(int(np.count_nonzero(original == label)) for label in range(5))
    for draw in schedule:
        np.testing.assert_array_equal(original[draw.source_indices], draw.source_folds)
        assert tuple(Counter(draw.source_folds).values()) == original_counts
        assert draw.receipt.source_fold_counts == original_counts
        assert np.all(draw.source_folds[1:] >= draw.source_folds[:-1])
        for unit in np.unique(draw.source_indices):
            assert len(np.unique(draw.source_folds[draw.source_indices == unit])) == 1


def test_receipt_counts_and_kish_ess_match_independent_python_frequency_oracles(schedule):
    for draw in schedule:
        source_counts = Counter(int(index) for index in draw.source_indices)
        external_counts = Counter(int(index) for index in draw.external_indices)
        receipt = draw.receipt
        assert receipt.source_unique_count == len(source_counts)
        assert receipt.external_unique_count == len(external_counts)
        assert receipt.source_effective_count == 71**2 / sum(x**2 for x in source_counts.values())
        assert receipt.external_effective_count == 7**2 / sum(
            x**2 for x in external_counts.values()
        )
        for label in range(5):
            frequencies = Counter(
                int(index)
                for index, fold in zip(draw.source_indices, draw.source_folds, strict=True)
                if fold == label
            )
            assert receipt.source_fold_unique_counts[label] == len(frequencies)
            assert receipt.source_fold_effective_counts[label] == sum(
                frequencies.values()
            ) ** 2 / sum(x**2 for x in frequencies.values())


def test_exact_known_empirical_multiplicities_have_descriptive_ess_not_row_count():
    source, folds, external, receipt = _manual_draw()
    draw = TwoCohortDraw(source, folds, external, receipt)
    assert draw.receipt.source_count == 60
    assert draw.receipt.source_unique_count == 10
    assert draw.receipt.source_effective_count == 10.0
    assert draw.receipt.external_count == 4
    assert draw.receipt.external_unique_count == 2
    assert draw.receipt.external_effective_count == 1.6
    assert draw.receipt.source_fold_effective_counts == (2.0,) * 5


def test_unequal_strata_and_single_original_fold_unit_are_preserved():
    original = np.repeat(np.arange(5, dtype=np.int8), [1, 2, 3, 4, 50])
    for draw in generate_two_cohort_draws(
        source_folds=original, external_count=1, request_digest=_DIGEST
    ):
        assert draw.receipt.source_fold_counts == (1, 2, 3, 4, 50)
        assert draw.source_indices[0] == 0
        assert draw.receipt.source_fold_effective_counts[0] == 1.0
        assert draw.receipt.external_effective_count == 1.0
        np.testing.assert_array_equal(draw.external_indices, [0])
        np.testing.assert_array_equal(original[draw.source_indices], draw.source_folds)


def test_two_rng_streams_do_not_advance_each_other(schedule):
    changed_external = generate_two_cohort_draws(
        source_folds=_folds(), external_count=31, request_digest=_DIGEST
    )
    changed_source = generate_two_cohort_draws(
        source_folds=_folds(93), external_count=7, request_digest=_DIGEST
    )
    for original, different_external, different_source in zip(
        schedule, changed_external, changed_source, strict=True
    ):
        np.testing.assert_array_equal(original.source_indices, different_external.source_indices)
        np.testing.assert_array_equal(original.external_indices, different_source.external_indices)


def test_reproducible_schedule_changes_with_request_binding_and_not_global_rng(schedule):
    before = np.random.get_state()
    repeated = generate_two_cohort_draws(
        source_folds=_folds(), external_count=7, request_digest=_DIGEST
    )
    after = np.random.get_state()
    assert before[0] == after[0]
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]
    for first, second in zip(schedule, repeated, strict=True):
        np.testing.assert_array_equal(first.source_indices, second.source_indices)
        np.testing.assert_array_equal(first.external_indices, second.external_indices)
        assert first.receipt == second.receipt
    changed = generate_two_cohort_draws(
        source_folds=_folds(), external_count=7, request_digest="sha256:" + "b" * 64
    )
    assert any(
        not np.array_equal(a.source_indices, b.source_indices)
        for a, b in zip(schedule, changed, strict=True)
    )
    assert any(
        not np.array_equal(a.external_indices, b.external_indices)
        for a, b in zip(schedule, changed, strict=True)
    )


def test_noncontiguous_input_is_snapshotted_without_mutation_or_row_reordering(schedule):
    backing = np.repeat(_folds(), 2)
    view = backing[::2]
    expected = view.copy()
    generated = generate_two_cohort_draws(
        source_folds=view, external_count=7, request_digest=_DIGEST
    )
    np.testing.assert_array_equal(view, expected)
    backing[:] = 0
    for first, second in zip(schedule, generated, strict=True):
        np.testing.assert_array_equal(first.source_indices, second.source_indices)
        np.testing.assert_array_equal(expected[second.source_indices], second.source_folds)


def test_maximum_sizes_are_bounded_exact_dtypes_and_all128_schedules_are_complete():
    draws = generate_two_cohort_draws(
        source_folds=_folds(10_000), external_count=10_000, request_digest=_DIGEST
    )
    assert len(draws) == 128
    assert (
        sum(
            a.nbytes
            for draw in draws
            for a in (draw.source_indices, draw.source_folds, draw.external_indices)
        )
        == 21_760_000
    )
    for draw in draws:
        assert draw.source_indices.dtype == np.int64
        assert draw.external_indices.dtype == np.int64
        assert draw.source_folds.dtype == np.int8
        assert (
            len(draw.source_indices)
            == len(draw.source_folds)
            == len(draw.external_indices)
            == 10_000
        )
        assert np.min(draw.source_indices) >= 0
        assert np.max(draw.source_indices) < 10_000
        assert np.min(draw.external_indices) >= 0
        assert np.max(draw.external_indices) < 10_000


@pytest.mark.parametrize("name", ["source_indices", "source_folds", "external_indices"])
def test_arrays_are_bytes_backed_and_cannot_be_reenabled_for_writing(schedule, name):
    values = getattr(schedule[0], name)
    assert type(values.base) is bytes
    assert not values.flags.writeable
    assert not values.flags.owndata
    with pytest.raises(ValueError):
        values[0] = 0
    with pytest.raises(ValueError):
        values.setflags(write=True)


def test_direct_construction_defensively_snapshots_mutable_inputs():
    source, folds, external, receipt = _manual_draw()
    draw = TwoCohortDraw(source, folds, external, receipt)
    wanted_source = source.copy()
    wanted_folds = folds.copy()
    source[:] = 59
    folds[:] = 4
    external[:] = 3
    np.testing.assert_array_equal(draw.source_indices, wanted_source)
    np.testing.assert_array_equal(draw.source_folds, wanted_folds)
    np.testing.assert_array_equal(draw.external_indices, [0, 0, 0, 1])
    with pytest.raises(FrozenInstanceError):
        draw.receipt = receipt
    with pytest.raises(FrozenInstanceError):
        receipt.source_count = 61


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_transient_draw_refuses_all_pickle_protocols_and_state_export(schedule, protocol):
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(schedule[0], protocol=protocol)
    with pytest.raises(TypeError, match="cannot be serialized"):
        schedule[0].__getstate__()


def test_only_aggregate_receipt_and_profile_have_normal_json_serialization(schedule):
    draw = schedule[0]
    fields = asdict(draw.receipt)
    assert set(fields) == {
        "draw_ordinal",
        "source_count",
        "external_count",
        "source_unique_count",
        "external_unique_count",
        "source_fold_counts",
        "source_fold_unique_counts",
        "source_effective_count",
        "external_effective_count",
        "source_fold_effective_counts",
    }
    assert json.loads(json.dumps(fields))["source_count"] == 71
    assert "source_indices" not in repr(draw)
    assert "external_indices" not in repr(draw)
    assert "source_folds=" not in repr(draw)
    with pytest.raises(TypeError):
        json.dumps(draw)
    with pytest.raises(TypeError):
        json.dumps(asdict(draw))
    profile = resampling.resampling_profile()
    assert profile.profile_id == "cptac-gbm-two-cohort-patient-bootstrap/1.0.0"
    assert profile.cohort_independence_established is False
    assert profile.support_or_power_admitted is False
    assert "descriptive only" in profile.effective_count
    json.dumps(asdict(profile), allow_nan=False)
    with pytest.raises(FrozenInstanceError):
        profile.replicates = 256


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        True,
        np.int8(1),
        np.zeros((60, 1), dtype=np.int8),
        np.zeros(60, dtype=np.int64),
        np.zeros(60, dtype=np.float64),
        np.zeros(60, dtype=bool),
        _folds(59),
        _folds(10_001),
    ],
)
def test_invalid_source_contract_is_rejected_without_contents_in_errors(value):
    with pytest.raises(ResamplingError, match="source fold array is invalid"):
        generate_two_cohort_draws(source_folds=value, external_count=7, request_digest=_DIGEST)


@pytest.mark.parametrize(
    "value",
    [
        np.zeros(60, dtype=np.int8),
        np.resize(np.array([-1, 0, 1, 2, 3, 4], dtype=np.int8), 60),
        np.resize(np.arange(6, dtype=np.int8), 60),
    ],
)
def test_missing_or_out_of_range_original_fold_labels_are_rejected(value):
    with pytest.raises(ResamplingError, match="source fold labels"):
        generate_two_cohort_draws(source_folds=value, external_count=7, request_digest=_DIGEST)


@pytest.mark.parametrize(
    "value", [True, False, np.int64(7), np.int32(7), 7.0, "7", None, 0, -1, 10_001]
)
def test_external_count_requires_bounded_exact_python_integer(value):
    with pytest.raises(ResamplingError, match="external patient count"):
        generate_two_cohort_draws(
            source_folds=_folds(), external_count=value, request_digest=_DIGEST
        )


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        b"sha256:" + b"a" * 64,
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "a" * 64 + "\n",
        "private-patient-label",
    ],
)
def test_digest_requires_exact_canonical_lowercase_sha256_and_errors_are_sanitized(value):
    with pytest.raises(ResamplingError, match=r"^request digest is invalid$") as caught:
        generate_two_cohort_draws(source_folds=_folds(), external_count=7, request_digest=value)
    assert "private-patient-label" not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("draw_ordinal", True),
        ("draw_ordinal", 128),
        ("source_count", 59),
        ("external_count", 0),
        ("source_unique_count", 4),
        ("external_unique_count", 5),
        ("source_fold_counts", [12] * 5),
        ("source_fold_counts", (12,) * 4),
        ("source_fold_counts", (11, 12, 12, 12, 12)),
        ("source_fold_counts", (True, 12, 12, 12, 23)),
        ("source_fold_unique_counts", (1, 1, 1, 1, 1)),
        ("source_fold_unique_counts", (13, 1, 1, 1, 1)),
        ("source_effective_count", 0.0),
        ("source_effective_count", 11.0),
        ("source_effective_count", float("nan")),
        ("external_effective_count", float("inf")),
        ("external_effective_count", 2),
        ("source_fold_effective_counts", (2.0,) * 4),
        ("source_fold_effective_counts", (0.0,) * 5),
        ("source_fold_effective_counts", (2,) * 5),
    ],
)
def test_direct_receipts_reject_invalid_count_ess_and_tuple_contracts(field, value):
    *_, receipt = _manual_draw()
    with pytest.raises(ResamplingError):
        replace(receipt, **{field: value})


@pytest.mark.parametrize("field", ["source_indices", "source_folds", "external_indices"])
def test_direct_draw_rejects_wrong_dtype_and_shape(field):
    source, folds, external, receipt = _manual_draw()
    args = {
        "source_indices": source,
        "source_folds": folds,
        "external_indices": external,
        "receipt": receipt,
    }
    for invalid in [args[field].astype(np.float64), args[field][:, None], args[field][:-1]]:
        with pytest.raises(ResamplingError, match="array contracts"):
            TwoCohortDraw(**{**args, field: invalid})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_indices", -1),
        ("source_indices", 60),
        ("external_indices", -1),
        ("external_indices", 4),
        ("source_folds", -1),
        ("source_folds", 5),
    ],
)
def test_direct_draw_rejects_out_of_bounds_rows_or_folds(field, value):
    source, folds, external, receipt = _manual_draw()
    args = {
        "source_indices": source,
        "source_folds": folds,
        "external_indices": external,
        "receipt": receipt,
    }
    args[field][0] = value
    with pytest.raises(ResamplingError, match="indices or fold blocks"):
        TwoCohortDraw(**args)


def test_direct_draw_rejects_same_original_source_unit_in_two_different_folds():
    source, folds, external, receipt = _manual_draw()
    source[12] = source[0]
    with pytest.raises(ResamplingError, match="cross fold blocks"):
        TwoCohortDraw(source, folds, external, receipt)


def test_direct_draw_rejects_nonmonotone_fold_blocks_receipt_mismatch_and_wrong_receipt_type():
    source, folds, external, receipt = _manual_draw()
    swapped = folds.copy()
    swapped[0], swapped[12] = swapped[12], swapped[0]
    with pytest.raises(ResamplingError, match="indices or fold blocks"):
        TwoCohortDraw(source, swapped, external, receipt)
    with pytest.raises(ResamplingError, match="aggregate receipt"):
        TwoCohortDraw(source, folds, external, replace(receipt, source_effective_count=9.0))
    with pytest.raises(ResamplingError, match="draw receipt is invalid"):
        TwoCohortDraw(source, folds, external, None)
