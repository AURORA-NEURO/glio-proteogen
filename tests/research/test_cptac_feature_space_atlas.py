"""Independent source-only coverage, capacity, variation and private-array oracles."""

from __future__ import annotations

import hashlib
import json
import pickle
from collections import Counter
from dataclasses import FrozenInstanceError, asdict, replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity
from glio_proteogen.research.cptac_gbm_feature_space import atlas, contracts
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    STATES,
    FeatureAxis,
    FeatureMatrix,
    FeatureSpaceError,
    GeneMeasurements,
)

SOURCE_DIGEST = "sha256:" + "a" * 64
EXTERNAL_DIGEST = "sha256:" + "b" * 64


def _gene(index, *, symbol=None):
    return GeneIdentity(
        f"HGNC:{index}", symbol or f"SYNTHETIC{index}", str(index), f"ENSG{index:011d}"
    )


def _axis(count=1):
    return FeatureAxis(
        tuple(sorted((_gene(i) for i in range(1, count + 1)), key=lambda g: g.hgnc_id))
    )


def _digest(value):
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _matrix(*, features=1, cases=72, values=None, states=None, axis=None, candidate=SOURCE_DIGEST):  # noqa: PLR0913
    axis = axis or _axis(features)
    shape = len(axis.identities), cases
    if values is None:
        values = tuple(
            np.tile(np.arange(cases, dtype=np.float64) + offset, (shape[0], 1))
            for offset in (1, 2, 3)
        )
    if states is None:
        states = tuple(np.where(np.isfinite(value), 0, 5).astype(np.uint8) for value in values)
    return FeatureMatrix(axis, candidate, *values, *states)


def _folds(cases=72):
    return np.array([index % 5 for index in range(cases)], dtype=np.int8)


def _capacity_matrix(counts):
    records = [(fold, True) for fold, count in enumerate(counts) for _ in range(count)]
    records.extend((index % 5, False) for index in range(max(5, 60 - len(records))))
    cases = len(records)
    values = [np.arange(cases, dtype=np.float64)[None, :] + 1 for _ in range(3)]
    for index, (_fold, complete) in enumerate(records):
        if not complete:
            values[2][0, index] = np.nan
    return _matrix(cases=cases, values=tuple(values)), np.array(
        [row[0] for row in records], dtype=np.int8
    )


def _coverage_oracle(matrix, row):
    arrays = (matrix.cnv[row], matrix.rna[row], matrix.protein[row])
    states = (matrix.cnv_states[row], matrix.rna_states[row], matrix.protein_states[row])
    observed = [[int(code) == 0 for code in state] for state in states]
    patterns = Counter(
        "".join("1" if axis[i] else "0" for axis in observed) for i in range(matrix.case_count)
    )
    return {
        "observed": tuple(sum(axis) for axis in observed),
        "pairs": (
            sum(r and p for r, p in zip(observed[1], observed[2], strict=True)),
            sum(c and p for c, p in zip(observed[0], observed[2], strict=True)),
        ),
        "joint": patterns["111"],
        "patterns": tuple(patterns[f"{value:03b}"] for value in range(8)),
        "states": tuple(
            tuple(sum(int(code) == value for code in state) for value in range(6))
            for state in states
        ),
        "zeros": tuple(sum(float(value) == 0 for value in array) for array in arrays),
    }


def test_all_eight_patterns_and_six_states_conserve_actual_paired_support():
    states = [np.empty((2, 72), dtype=np.uint8) for _ in range(3)]
    for axis, bit in enumerate((4, 2, 1)):
        missing = 0
        for case in range(72):
            if (case % 8) & bit:
                states[axis][0, case] = 0
            else:
                states[axis][0, case] = missing % 5 + 1
                missing += 1
    # Same marginal counts; RNA/protein co-occur and CNV occurs in different patients.
    for case in range(72):
        states[0][1, case] = 0 if case >= 36 else 5
        states[1][1, case] = states[2][1, case] = 0 if case < 36 else 5
    values = [np.where(state == 0, np.arange(72)[None, :] + 1.0, np.nan) for state in states]
    for axis in range(3):
        first = next(case for case in range(72) if states[axis][0, case] == 0)
        values[axis][0, first] = -0.0 if axis == 2 else 0.0
    matrix = _matrix(features=2, values=tuple(values), states=tuple(states))
    result = atlas.build_source_catalog(matrix, _folds())
    assert len(result.genes) == len(matrix.axis.identities) == 2
    for index, row in enumerate(result.genes):
        coverage, expected = row.coverage, _coverage_oracle(matrix, index)
        assert coverage.identity == matrix.axis.identities[index]
        assert coverage.candidate_specimens == 72
        assert (
            coverage.observed_cnv,
            coverage.observed_rna,
            coverage.observed_protein,
        ) == expected["observed"]
        assert (coverage.rna_protein_complete, coverage.cnv_protein_complete) == expected["pairs"]
        assert coverage.joint_complete == expected["joint"]
        assert coverage.pattern_counts_cnv_rna_protein == expected["patterns"]
        assert (
            coverage.cnv_state_counts,
            coverage.rna_state_counts,
            coverage.protein_state_counts,
        ) == expected["states"]
        assert (coverage.zero_cnv, coverage.zero_rna, coverage.zero_protein) == expected["zeros"]
        assert sum(coverage.pattern_counts_cnv_rna_protein) == 72
        assert all(sum(counts) == 72 for counts in expected["states"])
    assert result.genes[0].coverage.pattern_counts_cnv_rna_protein == (9,) * 8
    assert all(
        count > 0
        for counts in (
            result.genes[0].coverage.cnv_state_counts,
            result.genes[0].coverage.rna_state_counts,
            result.genes[0].coverage.protein_state_counts,
        )
        for count in counts
    )
    paired = result.genes[1].coverage
    assert paired.observed_rna == paired.observed_protein == paired.observed_cnv == 36
    assert (
        paired.rna_protein_complete == 36
        and paired.cnv_protein_complete == paired.joint_complete == 0
    )
    assert paired.rna_protein_complete != paired.observed_rna * paired.observed_protein / 72
    assert result.state_order == STATES
    assert result.pattern_order_cnv_rna_protein == tuple(f"{i:03b}" for i in range(8))


def test_structural_protein_absence_blank_and_finite_zero_are_not_interchangeable():
    values = [np.ones((3, 72), dtype=np.float64) for _ in range(3)]
    values[2][:2] = np.nan
    values[2][2] = 0
    states = [np.zeros((3, 72), dtype=np.uint8) for _ in range(3)]
    states[2][0], states[2][1] = 1, 5
    matrix = _matrix(features=3, values=tuple(values), states=tuple(states))
    rows = atlas.build_source_catalog(matrix, _folds()).genes
    assert [row.coverage.protein_feature_present for row in rows] == [False, True, True]
    assert [row.coverage.observed_protein for row in rows] == [0, 0, 72]
    assert [row.coverage.zero_protein for row in rows] == [0, 0, 72]
    assert rows[0].coverage.protein_state_counts == (0, 72, 0, 0, 0, 0)
    assert rows[1].coverage.protein_state_counts == (0, 0, 0, 0, 0, 72)
    assert rows[2].count_capacity.all_five_fold_count_support_possible is True
    assert rows[2].training_variation.protein_contexts_with_variation == 0


@pytest.mark.parametrize(
    ("counts", "supported"),
    [
        ((12, 12, 12, 12, 12), True),
        ((12, 12, 12, 12, 11), False),
        ((15, 12, 12, 12, 12), True),
        ((16, 12, 12, 12, 11), False),
        ((19, 19, 11, 11, 10), True),
        ((20, 19, 11, 10, 10), False),
        ((3, 18, 17, 17, 17), True),
        ((2, 18, 18, 17, 17), False),
        ((0, 18, 18, 18, 18), False),
        ((0, 0, 0, 0, 0), False),
    ],
)
def test_joint_validation_outer_and_twenty_ordered_inner_count_boundaries(counts, supported):
    matrix, folds = _capacity_matrix(counts)
    result = atlas.build_source_catalog(matrix, folds)
    capacity = result.genes[0].count_capacity
    total = sum(counts)
    outer = [sum(counts[other] for other in range(5) if other != held) for held in range(5)]
    inner = [
        sum(counts[other] for other in range(5) if other not in (held, inner))
        for held in range(5)
        for inner in range(5)
        if held != inner
    ]
    assert len(inner) == 20
    assert capacity.joint_complete == total
    assert capacity.fold_joint_counts == counts
    assert capacity.minimum_validation_joint == min(counts)
    assert capacity.minimum_outer_training_joint == min(outer)
    assert capacity.minimum_inner_training_joint == min(inner)
    assert capacity.all_five_fold_count_support_possible is supported
    assert result.count_supported_genes == int(supported)
    assert result.source_count_candidate_hgnc_digest == _digest(["HGNC:1"] if supported else [])
    if counts == (2, 18, 18, 17, 17):
        assert sum(count >= 3 for count in counts) == 4
        assert total >= 60 and min(outer) >= 48 and min(inner) >= 32
        assert not supported  # Four adequate folds cannot replace this profile's all-five rule.


def test_twenty_six_variation_contexts_use_only_each_contexts_joint_complete_cases():
    folds = np.repeat(np.arange(5, dtype=np.int8), [15, 15, 14, 14, 14])
    values = [np.ones((4, 72), dtype=np.float64) for _ in range(3)]
    values[0][0] = 2  # Constant CNV, varying RNA, constant protein.
    values[1][0] = np.arange(72, dtype=np.float64)
    values[2][0] = 3
    values[1][1, 0] = 2  # Only one fold contains the different RNA value.
    values[1][2, 0] = 2
    values[0][2, 0] = np.nan  # That value cannot vary the joint-complete design.
    for array in values:
        array[3, 1:] = np.nan  # One joint-complete observation never proves variation.
    matrix = _matrix(features=4, values=tuple(values))
    result = atlas.build_source_catalog(matrix, folds)
    excluded = (
        [set()]
        + [{outer} for outer in range(5)]
        + [{outer, inner} for outer in range(5) for inner in range(5) if outer != inner]
    )
    assert len(excluded) == 26
    for index, row in enumerate(result.genes):
        expected = []
        for array in (matrix.cnv[index], matrix.rna[index], matrix.protein[index]):
            varied = 0
            for held in excluded:
                rows = [
                    case
                    for case in range(72)
                    if int(folds[case]) not in held
                    and all(
                        np.isfinite(axis[index, case])
                        for axis in (matrix.cnv, matrix.rna, matrix.protein)
                    )
                ]
                varied += len({float(array[case]) for case in rows}) >= 2
            expected.append(varied)
        actual = row.training_variation
        assert actual.training_contexts == 26
        assert (
            actual.cnv_contexts_with_variation,
            actual.rna_contexts_with_variation,
            actual.protein_contexts_with_variation,
        ) == tuple(expected)
    assert result.genes[1].training_variation.rna_contexts_with_variation == 17
    assert result.genes[2].training_variation.rna_contexts_with_variation == 0
    assert result.genes[3].training_variation == atlas.TrainingVariationDiagnostics(26, 0, 0, 0)
    assert result.genes[0].count_capacity.all_five_fold_count_support_possible
    assert result.variation_is_a_gate is result.fit_eligibility_established is False


def test_count_support_allows_constant_zero_coordinates_without_claiming_a_fit():
    matrix = _matrix(values=tuple(np.zeros((1, 72), dtype=np.float64) for _ in range(3)))
    before = tuple(value.copy() for value in (matrix.cnv, matrix.rna, matrix.protein))
    result = atlas.build_source_catalog(matrix, _folds())
    row = result.genes[0]
    assert result.count_supported_genes == 1 and row.coverage.joint_complete == 72
    assert row.training_variation == atlas.TrainingVariationDiagnostics(26, 0, 0, 0)
    assert (
        result.fit_eligibility_established
        is result.numerical_rank_or_convergence_established
        is False
    )
    inputs = matrix.gene("HGNC:1")
    fit = transfer.fit_source_gene(inputs.cnv, inputs.rna, inputs.protein, _folds())
    assert not fit.receipt.accepted
    for old, current in zip(before, (matrix.cnv, matrix.rna, matrix.protein), strict=True):
        np.testing.assert_array_equal(old, current)


def test_exact_distinctness_has_no_variance_epsilon_and_does_not_establish_rank():
    values = [np.ones((3, 72), dtype=np.float64) for _ in range(3)]
    values[1][0] = 0
    values[1][0, 1::2] = -0.0
    values[1][1] = 0
    values[1][1, 0] = np.nextafter(0.0, 1.0)
    values[0][2] = np.arange(72)
    values[1][2] = 2 * values[0][2]
    values[2][2] = 3 * values[0][2]
    catalog = atlas.build_source_catalog(_matrix(features=3, values=tuple(values)), _folds())
    assert catalog.genes[0].training_variation.rna_contexts_with_variation == 0
    assert catalog.genes[1].training_variation.rna_contexts_with_variation == 17
    assert catalog.genes[2].training_variation == atlas.TrainingVariationDiagnostics(26, 26, 26, 26)
    assert catalog.count_supported_genes == 3
    assert catalog.numerical_rank_or_convergence_established is False


def test_nonpanel_gene_extraction_is_directly_usable_by_existing_source_fitter():
    rng = np.random.default_rng(15337)
    cnv, rna = rng.uniform(0.5, 5, 72), rng.uniform(1, 9, 72)
    protein = 1 + 2 * rna + 0.4 * cnv + rng.normal(scale=0.1, size=72)
    matrix = _matrix(
        axis=FeatureAxis((_gene(90001, symbol="SYNTHETIC_NONPANEL"),)),
        values=tuple(value[None, :] for value in (cnv, rna, protein)),
    )
    folds = transfer.deterministic_patient_folds(tuple(f"SYNTHETIC-{i:03d}" for i in range(72)))
    inputs = matrix.gene("HGNC:90001")
    assert isinstance(inputs, GeneMeasurements)
    fit = transfer.fit_source_gene(inputs.cnv, inputs.rna, inputs.protein, folds)
    assert fit.receipt.accepted, fit.receipt.failure_reason
    assert fit.receipt.complete_count == fit.receipt.common_oof_count == 72
    assert fit.receipt.valid_outer_folds == 5
    assert atlas.build_source_catalog(matrix, folds).model_fits_performed is False


def test_gene_axis_and_both_catalog_digests_match_independent_canonical_json():
    axis = FeatureAxis((_gene(10), _gene(2)))  # Lexical order differs from numeric order.
    assert axis.hgnc_ids == ("HGNC:10", "HGNC:2")
    assert axis.digest == _digest([asdict(identity) for identity in axis.identities])
    matrix = _matrix(axis=axis)
    source = atlas.build_source_catalog(matrix, _folds())
    external = atlas.project_external_coverage(
        source, _matrix(axis=axis, cases=56, candidate=EXTERNAL_DIGEST)
    )
    assert source.digest == _digest(asdict(source))
    assert external.digest == _digest(asdict(external))
    assert source.feature_axis_digest == external.feature_axis_digest == axis.digest
    assert external.source_catalog_digest == source.digest
    assert source.source_fold_assignment_digest == _digest([int(value) for value in _folds()])
    assert source.source_count_candidate_hgnc_digest == _digest(["HGNC:10", "HGNC:2"])
    assert source.measurement_matrix_bytes == matrix.measurement_bytes == 2 * 72 * 8 * 3
    assert source.availability_matrix_bytes == 2 * 72 * 3


@pytest.mark.parametrize(
    ("external_cases", "sufficient"), [(1, False), (47, False), (48, True), (56, True)]
)
def test_external48_is_a_descriptive_count_flag_without_source_oof_requirement(
    external_cases, sufficient
):
    values = [np.ones((2, 72), dtype=np.float64) for _ in range(3)]
    values[2][1] = np.nan
    source = atlas.build_source_catalog(_matrix(features=2, values=tuple(values)), _folds())
    external = atlas.project_external_coverage(
        source, _matrix(features=2, cases=external_cases, candidate=EXTERNAL_DIGEST)
    )
    assert external.external_joint_minimum == 48
    assert external.external_count_sufficient_genes == 2 * int(sufficient)
    assert external.source_and_external_count_sufficient_genes == int(sufficient)
    assert (
        external.fit_or_transfer_eligibility_established
        is external.aligned_external_validation
        is False
    )
    assert external.model_fits_performed is external.selection_uses_external_values is False


def test_changed_external_availability_or_candidate_digest_cannot_change_source_catalog():
    source = atlas.build_source_catalog(_matrix(features=2), _folds())
    before, candidates = source.digest, source.source_count_candidate_hgnc_digest
    original = _matrix(features=2, cases=56, candidate=EXTERNAL_DIGEST)
    first = atlas.project_external_coverage(source, original)
    values = [value.copy() for value in (original.cnv, original.rna, original.protein)]
    values[2][0, :10] = np.nan
    changed = _matrix(features=2, cases=56, values=tuple(values), candidate="sha256:" + "c" * 64)
    second = atlas.project_external_coverage(source, changed)
    assert first.digest != second.digest
    assert second.external_count_sufficient_genes == 1
    assert first.source_catalog_digest == second.source_catalog_digest == source.digest == before
    assert source.source_count_candidate_hgnc_digest == candidates
    assert source.candidate_digest == SOURCE_DIGEST
    assert first.candidate_digest == EXTERNAL_DIGEST and second.candidate_digest != SOURCE_DIGEST
    assert first.source_axis_changed is second.source_axis_changed is False


@pytest.mark.parametrize("mode", ["profile", "hgnc", "symbol", "cross_reference", "more_genes"])
def test_external_projection_rejects_changed_source_identity_axis(mode):
    source = atlas.build_source_catalog(_matrix(), _folds())
    axis = _axis()
    if mode == "profile":
        source = replace(source, profile_id="another/1.0.0")
    elif mode == "hgnc":
        axis = FeatureAxis((_gene(2),))
    elif mode == "symbol":
        axis = FeatureAxis((replace(axis.identities[0], symbol="OTHER_SYNTHETIC"),))
    elif mode == "cross_reference":
        axis = FeatureAxis((replace(axis.identities[0], ensembl_gene_id=None),))
    else:
        axis = _axis(2)
    with pytest.raises(FeatureSpaceError):
        atlas.project_external_coverage(source, _matrix(axis=axis, cases=56))


def test_column_permutation_preserves_counts_and_variation_with_fold_binding_changed():
    matrix = _matrix(features=2)
    folds = _folds()
    permutation = np.random.default_rng(132).permutation(72)
    permuted = _matrix(
        features=2,
        values=tuple(value[:, permutation] for value in (matrix.cnv, matrix.rna, matrix.protein)),
        states=tuple(
            value[:, permutation]
            for value in (matrix.cnv_states, matrix.rna_states, matrix.protein_states)
        ),
    )
    first, second = (
        atlas.build_source_catalog(matrix, folds),
        atlas.build_source_catalog(permuted, folds[permutation]),
    )
    assert first.genes == second.genes
    assert first.source_fold_assignment_digest != second.source_fold_assignment_digest
    assert first.source_count_candidate_hgnc_digest == second.source_count_candidate_hgnc_digest


@pytest.mark.parametrize(
    "mode", ["list", "dtype", "shape", "missing", "negative", "outside", "short"]
)
def test_source_fold_contract_requires_exact_nonempty_five_fold_inventory(mode):
    matrix, folds = _matrix(), _folds()
    if mode == "list":
        folds = folds.tolist()
    elif mode == "dtype":
        folds = folds.astype(np.int64)
    elif mode == "shape":
        folds = folds[:, None]
    elif mode == "missing":
        folds[:] = 0
    elif mode == "negative":
        folds[0] = -1
    elif mode == "outside":
        folds[0] = 5
    else:
        matrix, folds = _matrix(cases=59), _folds(59)
    with pytest.raises(FeatureSpaceError):
        atlas.build_source_catalog(matrix, folds)


@pytest.mark.parametrize("mode", ["source_matrix", "external_matrix", "source_catalog"])
def test_atlas_entrypoints_require_validated_transient_inputs(mode):
    if mode == "source_matrix":
        with pytest.raises(FeatureSpaceError):
            atlas.build_source_catalog(object(), _folds())
    else:
        source = atlas.build_source_catalog(_matrix(), _folds())
        with pytest.raises(FeatureSpaceError):
            atlas.project_external_coverage(
                object() if mode == "source_catalog" else source,
                object() if mode == "external_matrix" else _matrix(),
            )


@pytest.mark.parametrize(
    "mode",
    ["empty", "list", "wrong_type", "unsorted", "duplicate_id", "duplicate_symbol", "too_many"],
)
def test_feature_axis_requires_bounded_unique_lexical_stable_identities(mode):
    identities = (_gene(1),)
    if mode == "empty":
        identities = ()
    elif mode == "list":
        identities = list(identities)
    elif mode == "wrong_type":
        identities = (object(),)
    elif mode == "unsorted":
        identities = (_gene(2), _gene(10))
    elif mode == "duplicate_id":
        identities = (*identities, *identities)
    elif mode == "duplicate_symbol":
        identities = (_gene(1), _gene(2, symbol=identities[0].symbol))
    else:
        identities = (_gene(1),) * (contracts.MAX_FEATURES + 1)
    with pytest.raises(FeatureSpaceError):
        FeatureAxis(identities)


@pytest.mark.parametrize("bad", [None, 1, "", "a" * 64, "sha256:" + "A" * 64])
def test_matrix_candidate_digest_rejects_noncanonical_types_and_text(bad):
    with pytest.raises(FeatureSpaceError):
        _matrix(candidate=bad)


@pytest.mark.parametrize(
    "mode",
    [
        "values_list",
        "float32",
        "integer",
        "infinite",
        "states_list",
        "state_dtype",
        "state_code",
        "state_shape",
        "observed_nan",
        "unavailable_finite",
        "negative_rna",
        "negative_cnv",
        "one_dimension",
        "axis_rows",
        "axis_type",
        "case_shape",
        "empty_cases",
        "too_many_cases",
    ],
)
def test_feature_matrix_strict_shapes_states_and_coordinates_fail_closed(mode):  # noqa: C901, PLR0912
    axis = _axis()
    values = [np.ones((1, 72), dtype=np.float64) for _ in range(3)]
    states = [np.zeros((1, 72), dtype=np.uint8) for _ in range(3)]
    if mode == "values_list":
        values[0] = values[0].tolist()
    elif mode == "float32":
        values[0] = values[0].astype(np.float32)
    elif mode == "integer":
        values[0] = values[0].astype(np.int64)
    elif mode == "infinite":
        values[0][0, 0] = np.inf
    elif mode == "states_list":
        states[0] = states[0].tolist()
    elif mode == "state_dtype":
        states[0] = states[0].astype(np.int64)
    elif mode == "state_code":
        states[0][0, 0] = 6
    elif mode == "state_shape":
        states[0] = states[0][:, :-1]
    elif mode == "observed_nan":
        values[0][0, 0] = np.nan
    elif mode == "unavailable_finite":
        states[0][0, 0] = 5
    elif mode in ("negative_rna", "negative_cnv"):
        values[int(mode == "negative_rna")][0, 0] = -1
    elif mode == "one_dimension":
        values[0], states[0] = values[0][0], states[0][0]
    elif mode == "axis_rows":
        axis = _axis(2)
    elif mode == "axis_type":
        axis = object()
    elif mode == "case_shape":
        values[1], states[1] = values[1][:, :-1], states[1][:, :-1]
    else:
        cases = 0 if mode == "empty_cases" else 1001
        values = [np.ones((1, cases), dtype=np.float64) for _ in range(3)]
        states = [np.zeros((1, cases), dtype=np.uint8) for _ in range(3)]
    with pytest.raises(FeatureSpaceError) as error:
        FeatureMatrix(axis, SOURCE_DIGEST, *values, *states)
    assert "SYNTHETIC" not in str(error.value)


def test_feature_case_and_product_boundaries_are_inclusive_before_immutable_copy(monkeypatch):
    assert (contracts.MAX_FEATURES, contracts.MAX_CASES, contracts.MAX_CELLS) == (
        20_000,
        1_000,
        2_000_000,
    )
    assert len(_axis(20_000).identities) == 20_000
    assert _matrix(cases=1000).case_count == 1000
    # Exercise exact product arithmetic with a small injected test-only bound.
    monkeypatch.setattr(contracts, "MAX_CELLS", 4)
    assert _matrix(features=2, cases=2).measurement_bytes == 2 * 2 * 8 * 3

    def forbidden(_array):
        pytest.fail("oversize matrix reached dense immutable copy")

    monkeypatch.setattr(contracts, "immutable", forbidden)
    with pytest.raises(FeatureSpaceError):
        _matrix(features=2, cases=3)


@pytest.mark.parametrize(
    "mode",
    [
        "list",
        "float32",
        "misaligned",
        "two_dimensions",
        "empty",
        "oversize",
        "infinite",
        "negative_cnv",
        "negative_rna",
    ],
)
def test_extracted_gene_measurements_keep_strict_finite_nonnegative_assay_contract(mode):
    values = [np.ones(72, dtype=np.float64) for _ in range(3)]
    if mode == "list":
        values[0] = values[0].tolist()
    elif mode == "float32":
        values[0] = values[0].astype(np.float32)
    elif mode == "misaligned":
        values[0] = values[0][:-1]
    elif mode == "two_dimensions":
        values = [value[:, None] for value in values]
    elif mode in ("empty", "oversize"):
        values = [np.ones(0 if mode == "empty" else 1001, dtype=np.float64) for _ in range(3)]
    elif mode == "infinite":
        values[2][0] = np.inf
    else:
        values[int(mode == "negative_rna")][0] = -1
    with pytest.raises(FeatureSpaceError):
        GeneMeasurements(*values)


def test_private_arrays_are_defensively_copied_immutable_hidden_and_nonpickleable():
    arrays = [np.ones((1, 72), dtype=np.float64) for _ in range(3)]
    arrays[2][0, 0] = -743.72617  # Negative protein log2 ratios remain allowed.
    states = [np.zeros((1, 72), dtype=np.uint8) for _ in range(3)]
    matrix = _matrix(values=tuple(arrays), states=tuple(states))
    gene = matrix.gene("HGNC:1")
    arrays[2][:] = 999
    states[2][:] = 5
    assert matrix.protein[0, 0] == gene.protein[0] == -743.72617
    for private in (matrix, gene):
        assert "array" not in repr(private) and "743.72617" not in repr(private)
        with pytest.raises(TypeError):
            pickle.dumps(private)
        with pytest.raises(TypeError):
            private.__getstate__()
        with pytest.raises(TypeError):
            json.dumps(asdict(private))
        with pytest.raises(FrozenInstanceError):
            private.cnv = np.ones(72)
        for name in ("cnv", "rna", "protein"):
            array = getattr(private, name)
            assert not array.flags.writeable
            with pytest.raises(ValueError):
                array.setflags(write=True)
    for array in (matrix.cnv_states, matrix.rna_states, matrix.protein_states):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(FeatureSpaceError) as error:
        matrix.gene("PRIVATE-UNKNOWN-GENE")
    assert "PRIVATE" not in str(error.value)
    catalog = atlas.build_source_catalog(matrix, _folds())
    payload = json.dumps(asdict(catalog), allow_nan=False)
    assert "743.72617" not in payload
    assert (
        catalog.model_fits_performed
        is catalog.association_tested
        is catalog.values_imputed
        is False
    )
    assert catalog.values_transformed is catalog.selection_uses_external_values is False
    stack = [asdict(catalog)]
    while stack:
        item = stack.pop()
        assert not isinstance(item, np.ndarray)
        if isinstance(item, dict):
            assert not {
                "cnv",
                "rna",
                "protein",
                "values",
                "folds",
                "predictions",
                "residuals",
                "case_id",
            }.intersection(item)
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            assert len(item) not in (56, 72, 128)
            stack.extend(item)


def _projection_receipt():
    return contracts.ProjectionReceipt(
        axis=contracts.RNA_AXIS,
        workflow="STAR - Counts",
        annotation_release="GENCODE v36",
        input_bytes=100,
        data_rows=5,
        gene_rows=1,
        summary_rows=4,
        versioned_gene_rows=1,
        par_y_gene_rows=0,
        duplicate_gene_symbol_groups=0,
        ambiguous_reference_gene_ids=0,
        missing_gene_rows=0,
        observed_zero_gene_rows=1,
        feature_axis_digest=_axis(2).digest,
        feature_count=2,
        state_counts=(1, 1, 0, 0, 0, 0),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"axis": "other_axis"},
        {"workflow": "another workflow"},
        {"annotation_release": "GENCODE v35"},
        {"input_bytes": 0},
        {"input_bytes": 10_000_001},
        {"data_rows": 6},
        {"gene_rows": 0},
        {"summary_rows": 3},
        {"feature_count": 20_001},
        {"par_y_gene_rows": True},
        {"versioned_gene_rows": -1},
        {"state_counts": [1, 1, 0, 0, 0, 0]},
        {"state_counts": (1, True, 0, 0, 0, 0)},
        {"state_counts": (1, 0, 0, 0, 0, 0)},
        {"feature_axis_digest": "not-a-digest"},
    ],
)
def test_projection_receipt_preserves_exact_workflow_and_complete_state_accounting(change):
    with pytest.raises(FeatureSpaceError):
        replace(_projection_receipt(), **change)


def test_projected_assay_contract_is_immutable_and_checks_its_complete_state_partition():
    receipt = _projection_receipt()
    values = np.array([0.0, np.nan], dtype=np.float64)
    states = np.array([0, 1], dtype=np.uint8)
    projection = contracts.ProjectedAssay(receipt, values, states)
    values[0], states[1] = 999, 5
    assert projection.values[0] == 0 and projection.states[1] == 1
    assert "values=" not in repr(projection) and "states=" not in repr(projection)
    for array in (projection.values, projection.states):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(TypeError):
        pickle.dumps(projection)
    with pytest.raises(TypeError):
        projection.__getstate__()
    with pytest.raises(FeatureSpaceError):
        contracts.ProjectedAssay(object(), projection.values, projection.states)
    with pytest.raises(FeatureSpaceError):
        contracts.ProjectedAssay(receipt, np.ones(3), np.zeros(3, dtype=np.uint8))
    with pytest.raises(FeatureSpaceError):
        contracts.ProjectedAssay(receipt, projection.values, np.array([0, 5], dtype=np.uint8))
