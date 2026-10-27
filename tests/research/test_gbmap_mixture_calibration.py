"""Independent rank, bounded-support and empirical-calibration oracles."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from glio_proteogen.research.gbmap_mixture_calibration import (
    POLICY_ID,
    BoundedUnknownMassCalibration,
    MixtureCalibrationError,
    calibrate_unknown_mass,
)


@pytest.mark.parametrize(
    ("coverage", "rank", "candidate", "source"),
    [
        (0.5, 3, 0.3, "calibration_order_statistic"),
        (0.8, 4, 0.4, "calibration_order_statistic"),
        (0.99, 5, 1.0, "known_unit_interval_support"),
    ],
)
def test_four_score_rank_oracles_never_replace_missing_rank_with_sample_maximum(
    coverage, rank, candidate, source
):
    result = calibrate_unknown_mass(
        (0.3, 0.1, 0.4, 0.2), target_specificity=coverage, hard_ceiling=None
    )
    assert result.policy_id == POLICY_ID == "bounded-unknown-mass-decimal-rank-v1"
    assert result.calibration_score_count == 4
    assert result.required_rank == rank
    assert result.rank_candidate == result.policy_threshold == candidate
    assert result.candidate_source == source
    assert result.threshold_rule_kind == "uncapped_rank_rule"
    assert result.observed_candidate_truncated is False
    assert result.accepted_calibration_score_count == min(rank, 4)
    assert result.empirical_calibration_specificity == min(rank, 4) / 4
    assert result.exchangeability_verified is False


@pytest.mark.parametrize(("n", "rank", "candidate"), [(18, 19, 1.0), (19, 19, 0.19)])
def test_nineteen_samples_are_needed_for_a_nontrivial_ninety_five_percent_rank(n, rank, candidate):
    result = calibrate_unknown_mass(tuple(i / 100 for i in range(1, n + 1)), hard_ceiling=None)
    assert result.required_rank == rank
    assert result.rank_candidate == candidate
    assert result.candidate_source == (
        "known_unit_interval_support" if n == 18 else "calibration_order_statistic"
    )


@pytest.mark.parametrize(
    ("n", "target", "rank", "candidate"),
    [(24, 0.28, 7, 0.07), (99, 0.07, 7, 0.07), (2, math.nextafter(1 / 3, math.inf), 2, 0.02)],
)
def test_declared_decimal_rank_policy_avoids_both_directions_of_binary_rounding(
    n, target, rank, candidate
):
    result = calibrate_unknown_mass(
        tuple(i / 100 for i in range(1, n + 1)), target_specificity=target, hard_ceiling=None
    )
    assert result.required_rank == rank
    assert result.rank_candidate == candidate


@pytest.mark.parametrize(("target", "covered"), [(0.5, 3), (0.8, 4), (0.99, 5)])
def test_exact_five_way_heldout_enumeration_matches_rank_acceptance(target, covered):
    points = (0.1, 0.2, 0.3, 0.4, 0.5)
    decisions = []
    for held_index, held in enumerate(points):
        calibration = tuple(value for index, value in enumerate(points) if index != held_index)
        result = calibrate_unknown_mass(calibration, target_specificity=target, hard_ceiling=None)
        decisions.append(result.accepts(held))
    assert sum(decisions) == covered
    assert Fraction(sum(decisions), len(points)) == Fraction(covered, 5)


def test_ties_are_accepted_inclusively_and_omissions_are_flagged_strictly_above_cutoff():
    above = math.nextafter(0.2, math.inf)
    result = calibrate_unknown_mass(
        (0.2,) * 4, (0.2, above, 0.0, 0.9), target_specificity=0.5, hard_ceiling=None
    )
    assert result.rank_candidate == 0.2
    assert result.accepted_calibration_score_count == 4
    assert result.empirical_calibration_specificity == 1.0
    assert result.flagged_omission_score_count == 2
    assert result.empirical_omission_sensitivity == 0.5
    assert result.accepts(0.2) is True
    assert result.accepts(above) is False


def test_observed_one_and_support_fallback_one_have_distinct_origins():
    observed = calibrate_unknown_mass(
        (0.0, 1.0, 1.0), (0.0, 1.0), target_specificity=0.5, hard_ceiling=None
    )
    fallback = calibrate_unknown_mass(
        (0.1, 0.2, 0.3), (0.0, 1.0), target_specificity=0.99, hard_ceiling=None
    )
    assert observed.rank_candidate == fallback.rank_candidate == 1.0
    assert observed.candidate_source == "calibration_order_statistic"
    assert fallback.candidate_source == "known_unit_interval_support"
    for result in (observed, fallback):
        assert result.accepted_calibration_score_count == 3
        assert result.flagged_omission_score_count == 0
        assert result.accepts(1.0) is True


@pytest.mark.parametrize("ceiling", [None, 1.0])
def test_only_none_and_one_leave_the_declared_threshold_rule_uncapped(ceiling):
    result = calibrate_unknown_mass(
        (0.1, 0.2, 0.3, 0.4), target_specificity=0.8, hard_ceiling=ceiling
    )
    assert result.threshold_rule_kind == "uncapped_rank_rule"
    assert result.policy_threshold == 0.4


def test_ceiling_changes_the_rule_even_when_this_observed_candidate_is_not_truncated():
    result = calibrate_unknown_mass((0.01, 0.02, 0.03, 0.04), target_specificity=0.5)
    assert result.rank_candidate == result.policy_threshold == 0.03
    assert result.hard_ceiling == 0.35
    assert result.observed_candidate_truncated is False
    assert result.threshold_rule_kind == "ceiling_modified_rank_rule"
    assert result.exchangeability_verified is False


def test_clipped_support_fallback_does_not_mistake_empirical_specificity_one_for_a_rank_rule():
    result = calibrate_unknown_mass(
        (0.01, 0.02, 0.03, 0.04), (0.2, 0.4, 1.0), target_specificity=0.99
    )
    assert result.rank_candidate == 1.0
    assert result.policy_threshold == 0.35
    assert result.observed_candidate_truncated is True
    assert result.threshold_rule_kind == "ceiling_modified_rank_rule"
    assert result.empirical_calibration_specificity == 1.0
    assert result.empirical_omission_sensitivity == 2 / 3
    assert result.exchangeability_verified is False


def test_equal_ceiling_is_not_observed_truncation_but_next_lower_float_is():
    scores = (0.1, 0.2, 0.3, 0.4)
    equal = calibrate_unknown_mass(scores, target_specificity=0.5, hard_ceiling=0.3)
    lower = calibrate_unknown_mass(
        scores, target_specificity=0.5, hard_ceiling=math.nextafter(0.3, -math.inf)
    )
    assert equal.observed_candidate_truncated is False
    assert lower.observed_candidate_truncated is True
    assert equal.accepted_calibration_score_count == 3
    assert lower.accepted_calibration_score_count == 2
    assert equal.threshold_rule_kind == lower.threshold_rule_kind == "ceiling_modified_rank_rule"


def test_zero_ceiling_and_measured_zero_scores_keep_exact_tie_semantics():
    result = calibrate_unknown_mass(
        (0.0,) * 4, (0.0, 0.0, 1.0), target_specificity=0.5, hard_ceiling=0.0
    )
    assert result.rank_candidate == result.policy_threshold == 0.0
    assert result.observed_candidate_truncated is False
    assert result.accepted_calibration_score_count == 4
    assert result.flagged_omission_score_count == 1
    assert result.empirical_omission_sensitivity == 1 / 3


def test_omission_evaluation_cannot_select_or_change_the_known_score_cutoff():
    excluded = {
        "omission_score_count",
        "flagged_omission_score_count",
        "empirical_omission_sensitivity",
    }
    baseline = calibrate_unknown_mass((0.1, 0.2, 0.3, 0.4), target_specificity=0.5)
    for omitted in ((), (0.0,) * 5, (1.0,) * 7):
        result = calibrate_unknown_mass((0.1, 0.2, 0.3, 0.4), omitted, target_specificity=0.5)
        assert result.model_dump(exclude=excluded) == baseline.model_dump(exclude=excluded)


@pytest.mark.parametrize("omitted", [None, [], (), np.empty(0)])
def test_unavailable_omission_evaluation_is_none_rather_than_zero_sensitivity(omitted):
    result = calibrate_unknown_mass((0.1, 0.2), omitted, hard_ceiling=None)
    assert result.omission_score_count == result.flagged_omission_score_count == 0
    assert result.empirical_omission_sensitivity is None


def test_real_numeric_inputs_normalize_without_rejecting_integer_zeros_or_fraction_scores():
    scores = np.asarray((0, Fraction(1, 3), np.float32(0.5), np.int64(1)), dtype=object)
    result = calibrate_unknown_mass(scores, target_specificity=Fraction(1, 2), hard_ceiling=None)
    assert result.target_specificity == 0.5
    assert result.required_rank == 3
    assert result.rank_candidate == 0.5
    assert result.accepts(Fraction(1, 3)) is True
    assert result.accepts(np.int64(1)) is False


_INVALID_SCORES = (
    True,
    np.bool_(0),
    "0.3",
    Decimal("0.3"),
    complex(0.3, 0),
    math.nan,
    math.inf,
    -math.inf,
    -0.01,
    1.01,
    Fraction(2**54 + 1, 2**54),
    Fraction(-1, 10**400),
    None,
)


@pytest.mark.parametrize("value", _INVALID_SCORES)
@pytest.mark.parametrize("location", ["known", "omission", "application"])
def test_score_domains_are_checked_before_lossy_float_coercion(value, location):
    operations = {
        "known": lambda: calibrate_unknown_mass((0.1, value)),
        "omission": lambda: calibrate_unknown_mass((0.1, 0.2), (value,)),
        "application": lambda: calibrate_unknown_mass((0.1, 0.2)).accepts(value),
    }
    with pytest.raises(MixtureCalibrationError):
        operations[location]()


@pytest.mark.parametrize("values", [0.2, [[0.1, 0.2]], np.zeros((2, 1)), "0.2"])
@pytest.mark.parametrize("location", ["known", "omission"])
def test_score_vectors_must_be_one_dimensional(values, location):
    known = values if location == "known" else (0.1, 0.2)
    omitted = values if location == "omission" else None
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass(known, omitted)


@pytest.mark.parametrize("mask", [False, (True, False)])
def test_masked_scores_are_rejected_even_when_the_mask_is_empty(mask):
    scores = np.ma.array((0.1, 0.2), mask=mask)
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass(scores)
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass((0.1, 0.2), scores)


def test_empty_known_calibration_is_not_replaced_by_support_without_any_observations():
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass(())


@pytest.mark.parametrize(
    "value", [0, 1, True, np.bool_(0), "0.95", Decimal("0.95"), math.nan, math.inf, -0.1, 1.1]
)
def test_target_requires_strict_original_and_normalized_open_unit_interval(value):
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass((0.1, 0.2), target_specificity=value)


@pytest.mark.parametrize("target", [Fraction(1, 10**400), Fraction(2**54 - 1, 2**54)])
def test_original_interior_target_cannot_normalize_to_a_closed_endpoint(target):
    assert 0 < target < 1
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass((0.1, 0.2), target_specificity=target)


@pytest.mark.parametrize("value", [True, "0.35", Decimal("0.35"), math.nan, math.inf, -0.1, 1.1])
def test_ceiling_requires_real_closed_unit_interval_or_none(value):
    with pytest.raises(MixtureCalibrationError):
        calibrate_unknown_mass((0.1, 0.2), hard_ceiling=value)


def test_input_arrays_are_unchanged_and_permutations_leave_the_summary_unchanged():
    known = np.asarray((0.3, 0.1, 0.4, 0.2), dtype=np.float64)
    omitted = np.asarray((0.5, 0.0, 0.3), dtype=np.float64)
    before = (known.tobytes(), omitted.tobytes())
    known.flags.writeable = omitted.flags.writeable = False
    result = calibrate_unknown_mass(known, omitted, target_specificity=0.5)
    permuted = calibrate_unknown_mass(known[::-1], omitted[::-1], target_specificity=0.5)
    assert result == permuted
    assert (known.tobytes(), omitted.tobytes()) == before
    assert known.flags.writeable is omitted.flags.writeable is False


def test_json_roundtrip_is_closed_immutable_and_contains_only_scalar_summary_facts():
    result = calibrate_unknown_mass((0.11, 0.22, 0.33), (0.44, 0.55))
    assert BoundedUnknownMassCalibration.model_validate_json(result.model_dump_json()) == result
    document = result.model_dump(mode="json")
    assert all(not isinstance(value, (list, tuple, dict)) for value in document.values())
    assert document["exchangeability_verified"] is False
    with pytest.raises(ValueError):
        result.policy_threshold = 0.9
    document["raw_scores"] = [0.11, 0.22, 0.33]
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("source", ["observed", "fallback"])
@pytest.mark.parametrize("corruption", ["rejected_known", "flagged_omission"])
def test_threshold_one_rejects_impossible_serialized_bounded_outcomes(source, corruption):
    result = calibrate_unknown_mass(
        (0.0, 1.0, 1.0) if source == "observed" else (0.1, 0.2, 0.3),
        (0.1, 0.5, 1.0),
        target_specificity=0.5 if source == "observed" else 0.99,
        hard_ceiling=None,
    )
    assert result.policy_threshold == 1.0
    document = result.model_dump(mode="json")
    if corruption == "rejected_known":
        document["accepted_calibration_score_count"] = 2
        document["empirical_calibration_specificity"] = 2 / 3
    else:
        document["flagged_omission_score_count"] = 1
        document["empirical_omission_sensitivity"] = 1 / 3
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("claim", [True, 0, 1])
def test_serialized_summary_cannot_claim_or_coerce_verified_exchangeability(claim):
    document = calibrate_unknown_mass((0.1, 0.2)).model_dump(mode="json")
    document["exchangeability_verified"] = claim
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_id": "unreviewed-policy"},
        {"required_rank": 1},
        {"candidate_source": "known_unit_interval_support"},
        {"policy_threshold": 0.1},
        {"observed_candidate_truncated": True},
        {"threshold_rule_kind": "uncapped_rank_rule"},
        {"accepted_calibration_score_count": True},
        {"empirical_calibration_specificity": 0.1},
        {"empirical_omission_sensitivity": 0.0},
    ],
)
def test_serialized_summary_rejects_incoherent_rank_policy_and_counter_facts(changes):
    document = calibrate_unknown_mass((0.1, 0.2, 0.3, 0.4), target_specificity=0.5).model_dump(
        mode="json"
    )
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps({**document, **changes}))


@pytest.mark.parametrize("clipped", [False, True])
def test_serialized_counter_ratios_alone_cannot_contradict_the_adjusted_rank(clipped):
    result = calibrate_unknown_mass(
        (0.1, 0.2, 0.3, 0.4), target_specificity=0.8, hard_ceiling=0.25 if clipped else None
    )
    document = result.model_dump(mode="json")
    accepted = 4 if clipped else 2
    document["accepted_calibration_score_count"] = accepted
    document["empirical_calibration_specificity"] = accepted / 4
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps(document))


def test_serialized_support_fallback_cannot_invent_a_smaller_support_bound():
    result = calibrate_unknown_mass((0.1, 0.2, 0.3), hard_ceiling=None)
    document = result.model_dump(mode="json")
    document["rank_candidate"] = document["policy_threshold"] = 0.9
    with pytest.raises(ValueError):
        BoundedUnknownMassCalibration.model_validate_json(json.dumps(document))
