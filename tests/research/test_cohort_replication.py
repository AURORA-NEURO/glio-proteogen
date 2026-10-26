"""Independent analytic oracles and failure boundaries for aggregate replication."""

from __future__ import annotations

import json
import math
from hashlib import sha256
from statistics import NormalDist

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cohort_replication import (
    MAX_REQUEST_BYTES,
    ReplayRequest,
    ReplicationRequest,
    ReplicationResult,
    algorithm_profile,
    analyze_replication,
    engine,
    result_payload_digest,
    synthetic_demo_request,
    verify_replay,
)
from glio_proteogen.research.cohort_replication.canonical import require_byte_limit
from glio_proteogen.research.cohort_replication.contracts import (
    CohortEffect,
    DirectionAgreement,
    FeatureResult,
    Heterogeneity,
    MetaEstimate,
    PredictionInterval,
    ReplicationLimits,
    require_finite,
)


def request_for(values, standard_errors=None, *, features=None):
    """Generate a caller-owned aggregate fixture, never participant data."""

    size = len(values)
    errors = standard_errors if standard_errors is not None else [1.0] * size
    cohort_ids = [f"cohort-{index}" for index in range(size)]
    row = {
        "feature_id": "test-feature",
        "label": "Synthetic test feature",
        "effects": [
            {
                "cohort_id": identifier,
                "state": "observed" if value is not None else "missing",
                "estimate": value,
                "standard_error": error if value is not None else None,
            }
            for identifier, value, error in zip(cohort_ids, values, errors, strict=True)
        ],
    }
    return ReplicationRequest.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "analysis_id": "test-analysis",
                "disease_context": "glioblastoma_idh_wildtype",
                "estimand_id": "same-estimand",
                "effect_scale": "standardized_mean_difference",
                "contrast": "Fictitious A minus B",
                "independence_basis": "caller_declared_disjoint_participants",
                "cohorts": [
                    {
                        "cohort_id": identifier,
                        "label": f"Fictitious {identifier}",
                        "source_sha256": "sha256:" + sha256(identifier.encode()).hexdigest(),
                        "independence_group": identifier,
                        "sample_size": 50,
                    }
                    for identifier in cohort_ids
                ],
                "features": features if features is not None else [row],
            }
        )
    )


def modify(request, operation):
    payload = request.model_dump(mode="json")
    operation(payload)
    return ReplicationRequest.model_validate_json(json.dumps(payload))


def test_inverse_variance_fixed_and_zero_heterogeneity_hand_oracle():
    result = analyze_replication(request_for([1.0, 3.0], [1.0, 2.0])).features[0]
    assert result.support == "limited"
    assert result.fixed_effect.estimate == pytest.approx(1.4)
    assert result.fixed_effect.standard_error == pytest.approx(math.sqrt(0.8))
    assert result.fixed_effect.lower == pytest.approx(1.4 - 1.959963984540054 * math.sqrt(0.8))
    assert result.fixed_effect.upper == pytest.approx(1.4 + 1.959963984540054 * math.sqrt(0.8))
    assert result.random_effect == result.fixed_effect
    assert result.heterogeneity.q == pytest.approx(0.8)
    assert result.heterogeneity.degrees_of_freedom == 1
    assert result.heterogeneity.tau_squared == 0
    assert result.heterogeneity.i_squared_percent == 0
    assert result.prediction_interval is None
    assert result.leave_one_out == ()


def test_dersimonian_laird_heterogeneity_prediction_and_loo_hand_oracle():
    request = request_for([-1.0, 1.0, 3.0])
    result = analyze_replication(request).features[0]
    assert result.fixed_effect.estimate == 1.0
    assert result.heterogeneity.q == 8.0
    assert result.heterogeneity.degrees_of_freedom == 2
    assert result.heterogeneity.tau_squared == pytest.approx(3.0)
    assert result.heterogeneity.i_squared_percent == 75.0
    assert result.random_effect.estimate == 1.0
    assert result.random_effect.standard_error == pytest.approx(math.sqrt(4.0 / 3.0))
    spread = 1.959963984540054 * math.sqrt(13.0 / 3.0)
    assert result.prediction_interval.lower == pytest.approx(1.0 - spread)
    assert result.prediction_interval.upper == pytest.approx(1.0 + spread)
    assert result.prediction_interval.method == "approximate_normal_random_effects"
    assert len(result.leave_one_out) == 3
    assert [item.random_effect.estimate for item in result.leave_one_out] == [2.0, 1.0, 0.0]
    assert [item.delta_estimate for item in result.leave_one_out] == [1.0, 0.0, -1.0]
    assert all(item.observed_count == 2 for item in result.leave_one_out)
    assert result.direction_agreement.classification == "mixed_directions"


def test_unequal_variance_dl_oracle_and_extreme_weight_stability():
    result = analyze_replication(request_for([0.0, 10.0], [1.0, 1.0])).features[0]
    assert result.heterogeneity.q == 50.0
    assert result.heterogeneity.tau_squared == 49.0
    assert result.random_effect.estimate == 5.0
    assert result.random_effect.standard_error == 5.0
    assert result.p_value == pytest.approx(math.erfc(1.0 / math.sqrt(2.0)))
    extreme = analyze_replication(request_for([0.0, 100.0], [0.000001, 100.0])).features[0]
    assert extreme.fixed_effect.estimate == pytest.approx(1e-14)
    assert extreme.heterogeneity.tau_squared == 0
    assert extreme.random_effect.standard_error == pytest.approx(0.000001)


def test_unequal_weight_positive_heterogeneity_rational_oracle():
    # w=(1, 1/4, 1), mu_FE=23/9, Q=41/9, C=4/3,
    # tau2=23/12, w_RE=(12/35, 12/71, 12/35).
    result = analyze_replication(request_for([1.0, 3.0, 4.0], [1.0, 2.0, 1.0])).features[0]
    assert result.fixed_effect.estimate == pytest.approx(23.0 / 9.0)
    assert result.heterogeneity.q == pytest.approx(41.0 / 9.0)
    assert result.heterogeneity.tau_squared == pytest.approx(23.0 / 12.0)
    assert result.random_effect.estimate == pytest.approx(460.0 / 177.0)
    assert result.random_effect.standard_error == pytest.approx(math.sqrt(2485.0 / 2124.0))


@pytest.mark.parametrize("values", [[None, None, None], [0.7, None, None]])
def test_insufficient_coverage_abstains_without_fabricated_estimates(values):
    result = analyze_replication(request_for(values)).features[0]
    assert result.support == "abstained"
    assert result.observed_count == sum(value is not None for value in values)
    assert result.fixed_effect is None
    assert result.random_effect is None
    assert result.heterogeneity is None
    assert result.p_value is None
    assert result.adjusted_p_value == result.dependence_robust_adjusted_p_value == 1
    assert result.prediction_interval is None
    assert result.leave_one_out == ()
    assert result.direction_agreement.classification == "direction_indeterminate"
    assert result.direction_agreement.majority_fraction == (1.0 if values[0] is not None else None)


def test_missing_and_unsupported_are_visible_and_excluded_identically():
    request = request_for([1.0, 2.0, None, None])
    changed = modify(
        request, lambda payload: payload["features"][0]["effects"][3].update(state="unsupported")
    )
    feature = analyze_replication(changed).features[0]
    assert feature.observed_count == 2
    assert feature.total_count == 4
    assert [effect.state for effect in feature.effects] == [
        "observed",
        "observed",
        "missing",
        "unsupported",
    ]
    assert (
        feature.random_effect
        == analyze_replication(request_for([1.0, 2.0])).features[0].random_effect
    )
    assert any("without imputation" in reason for reason in feature.reasons)


def test_fixed_predeclared_bh_and_by_family_include_abstentions():
    p_values = [0.01, 0.04, 0.03]
    base = request_for([1.0, 1.0])
    rows = []
    for index, p_value in enumerate(p_values):
        row = base.features[0].model_dump(mode="json")
        row["feature_id"] = f"feature-{index}"
        for effect in row["effects"]:
            effect["estimate"] = NormalDist().inv_cdf(1.0 - p_value / 2.0)
            effect["standard_error"] = math.sqrt(2.0)
        rows.append(row)
    missing = request_for([None, None]).features[0].model_dump(mode="json")
    missing["feature_id"] = "feature-3"
    rows.append(missing)
    result = analyze_replication(request_for([1.0, 1.0], features=rows))
    assert result.family_size == 4
    assert [feature.adjusted_p_value for feature in result.features] == pytest.approx(
        [0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 1.0]
    )
    harmonic = 1.0 + 0.5 + 1.0 / 3.0 + 0.25
    assert [
        feature.dependence_robust_adjusted_p_value for feature in result.features
    ] == pytest.approx([0.04 * harmonic, 0.04 * 4 / 3 * harmonic, 0.04 * 4 / 3 * harmonic, 1.0])


@pytest.mark.parametrize(
    ("values", "classification", "counts"),
    [
        ([2.0, 3.0], "all_nominal_intervals_positive", (2, 0, 0)),
        ([-2.0, -3.0], "all_nominal_intervals_negative", (0, 2, 0)),
        ([0.2, 0.1], "direction_indeterminate", (2, 0, 0)),
        ([0.0, 0.0], "direction_indeterminate", (0, 0, 2)),
        ([1.0, -1.0], "mixed_directions", (1, 1, 0)),
    ],
)
def test_direction_is_descriptive_and_requires_each_nominal_interval(
    values, classification, counts
):
    feature = analyze_replication(request_for(values)).features[0]
    agreement = feature.direction_agreement
    assert agreement.classification == classification
    assert (agreement.positive_count, agreement.negative_count, agreement.zero_count) == counts
    if values == [0.0, 0.0]:
        assert feature.p_value == 1.0
        assert feature.heterogeneity.q == 0.0


def test_order_invariant_canonical_requests_numerics_receipts_and_replay():
    request = synthetic_demo_request()
    reordered = request.model_dump(mode="json")
    reordered["cohorts"].reverse()
    reordered["features"].reverse()
    for feature in reordered["features"]:
        feature["effects"].reverse()
    second = ReplicationRequest.model_validate_json(json.dumps(reordered))
    assert request == second
    assert request.request_digest == second.request_digest
    first_result = analyze_replication(request)
    second_result = analyze_replication(second)
    assert canonical_json_bytes(first_result.model_dump(mode="json")) == canonical_json_bytes(
        second_result.model_dump(mode="json")
    )
    assert verify_replay(second, first_result).valid
    assert ReplicationResult.model_validate_json(first_result.model_dump_json()) == first_result
    replay = ReplayRequest.model_validate_json(
        json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "result": first_result.model_dump(mode="json"),
            }
        )
    )
    assert replay.request == request
    assert replay.result == first_result


def test_self_rehashed_mutation_and_changed_source_are_rejected_on_replay():
    request = request_for([1.0, 2.0, 3.0])
    result = analyze_replication(request)
    payload = result.model_dump(mode="json")
    payload["features"][0]["random_effect"]["estimate"] += 0.01
    corrupted = ReplicationResult.model_validate_json(json.dumps(payload))
    corrupted = corrupted.model_copy(update={"result_digest": result_payload_digest(corrupted)})
    assert not verify_replay(request, corrupted).valid
    changed = modify(
        request, lambda item: item["cohorts"][0].update(source_sha256="sha256:" + "f" * 64)
    )
    verification = verify_replay(changed, result)
    assert not verification.valid
    assert verification.request_digest != result.request_digest
    assert verification.result_digest != result.result_digest


def test_sample_size_is_descriptive_and_does_not_weight_meta_estimates():
    request = request_for([0.0, 1.0, 4.0], [0.1, 0.3, 0.8])
    changed = modify(request, lambda payload: payload["cohorts"][0].update(sample_size=1_000_000))
    before, after = analyze_replication(request), analyze_replication(changed)
    assert before.features == after.features
    assert before.request_digest != after.request_digest


@pytest.mark.parametrize("field", ["cohort_id", "source_sha256", "independence_group"])
def test_duplicate_cohort_source_or_independence_is_rejected(field):
    with pytest.raises(ValidationError, match="unique"):
        modify(
            request_for([1.0, 2.0]),
            lambda payload: payload["cohorts"][1].update({field: payload["cohorts"][0][field]}),
        )


@pytest.mark.parametrize(
    "operation",
    [
        lambda payload: payload["features"].append(payload["features"][0]),
        lambda payload: payload["features"][0]["effects"][1].update(cohort_id="unknown"),
        lambda payload: payload["features"][0]["effects"][1].update(cohort_id="cohort-0"),
        lambda payload: payload["features"][0]["effects"].pop(),
        lambda payload: payload["cohorts"].pop(),
        lambda payload: payload.update(participant_measurements=[1.0]),
        lambda payload: payload.update(independence_basis="inferred_from_labels"),
        lambda payload: payload.update(effect_scale="arbitrary_mixed_units"),
        lambda payload: payload.update(disease_context="mixed_cancers"),
    ],
)
def test_malformed_matrices_and_undeclared_fields_fail_closed(operation):
    with pytest.raises(ValidationError):
        modify(request_for([1.0, 2.0]), operation)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimate", float("nan")),
        ("estimate", float("inf")),
        ("estimate", -100.01),
        ("estimate", 100.01),
        ("estimate", None),
        ("estimate", True),
        ("standard_error", 0.0),
        ("standard_error", 0.0000001),
        ("standard_error", 100.01),
        ("standard_error", None),
        ("standard_error", "0.1"),
        ("state", "left_censored"),
    ],
)
def test_nonfinite_out_of_bounds_or_incomplete_observations_fail(field, value):
    with pytest.raises(ValidationError):
        CohortEffect.model_validate(
            {
                "cohort_id": "one",
                "state": "observed",
                "estimate": 1.0,
                "standard_error": 0.1,
                field: value,
            }
        )


@pytest.mark.parametrize("state", ["missing", "unsupported"])
def test_non_observed_states_cannot_smuggle_numbers(state):
    with pytest.raises(ValidationError, match="cannot contain numbers"):
        CohortEffect(cohort_id="one", state=state, estimate=0.0)


def test_largest_allowed_matrix_is_bounded_and_replayable():
    request = request_for([0.2] * 16, [0.3] * 16)
    features = tuple(
        request.features[0].model_copy(update={"feature_id": f"feature-{index}"})
        for index in range(256)
    )
    request = request.model_copy(update={"features": features})
    result = analyze_replication(request)
    assert result.family_size == 256
    assert all(len(feature.leave_one_out) == 16 for feature in result.features)
    assert len(canonical_json_bytes(request.model_dump(mode="json"))) < MAX_REQUEST_BYTES
    assert verify_replay(request, result).valid


def test_over_limit_cohort_and_feature_counts_and_bypassed_models_are_rejected():
    with pytest.raises(ValidationError):
        request_for([0.2] * 17)
    request = request_for([1.0, 1.0])
    too_many = tuple(
        request.features[0].model_copy(update={"feature_id": f"feature-{index}"})
        for index in range(257)
    )
    with pytest.raises(ValidationError):
        analyze_replication(request.model_copy(update={"features": too_many}))
    invalid_effect = request.features[0].effects[0].model_copy(update={"standard_error": 0.0})
    invalid_feature = request.features[0].model_copy(
        update={"effects": (invalid_effect, request.features[0].effects[1])}
    )
    with pytest.raises(ValidationError):
        analyze_replication(request.model_copy(update={"features": (invalid_feature,)}))


def test_byte_limits_are_enforced_in_service_and_canonical_boundary(monkeypatch):
    request = request_for([1.0, 2.0])
    with pytest.raises(ValueError, match="byte limit"):
        require_byte_limit({"payload": "too long"}, 1)
    monkeypatch.setattr(engine, "MAX_REQUEST_BYTES", 1)
    with pytest.raises(ValueError, match="byte limit"):
        analyze_replication(request)
    monkeypatch.setattr(engine, "MAX_REQUEST_BYTES", MAX_REQUEST_BYTES)
    monkeypatch.setattr(engine, "MAX_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="byte limit"):
        analyze_replication(request)


def test_profile_and_demo_make_approximation_and_fictitious_sources_explicit():
    profile = algorithm_profile()
    assert profile.profile_id == "glioma-cohort-replication/1.0.0"
    assert profile.synthetic_demo_only
    assert profile.limits == ReplicationLimits()
    assert any("Benjamini-Yekutieli" in method for method in profile.methods)
    assert any("Hartung-Knapp" in assumption for assumption in profile.assumptions)
    assert any("publication bias" in assumption for assumption in profile.assumptions)
    demo = synthetic_demo_request()
    result = analyze_replication(demo)
    assert all("Fictitious" in cohort.label for cohort in demo.cohorts)
    assert all("synthetic" in feature.label.lower() for feature in demo.features)
    assert {feature.support for feature in result.features} == {"limited", "abstained"}
    assert result.contains_participant_data is False
    assert all(feature.support != "supported" for feature in result.features)


def test_contracts_are_frozen_and_invalid_result_states_fail():
    result = analyze_replication(request_for([1.0, 2.0]))
    with pytest.raises(ValidationError):
        result.analysis_id = "changed"
    with pytest.raises(ValidationError, match="contain"):
        MetaEstimate(estimate=0.0, standard_error=1.0, lower=1.0, upper=2.0, p_value=0.5)
    with pytest.raises(ValidationError, match="ordered"):
        PredictionInterval(lower=2.0, upper=1.0)
    with pytest.raises(ValidationError):
        Heterogeneity(q=-1.0, degrees_of_freedom=1, i_squared_percent=0.0, tau_squared=0.0)
    with pytest.raises(ValidationError):
        DirectionAgreement(
            positive_count=17,
            negative_count=0,
            zero_count=0,
            classification="direction_indeterminate",
        )
    with pytest.raises(ValueError, match="non-finite"):
        require_finite(float("inf"))
    assert require_finite(0.0) == 0.0
    payload = result.model_dump(mode="json")
    payload["family_size"] = 2
    with pytest.raises(ValidationError, match="family size"):
        ReplicationResult.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "update",
    [
        {"observed_count": 1},
        {"total_count": 3},
        {"support": "abstained"},
        {"fixed_effect": None},
        {"prediction_interval": {"lower": -1.0, "upper": 2.0}},
    ],
)
def test_result_coverage_and_support_reconcile(update):
    payload = analyze_replication(request_for([1.0, 2.0])).features[0].model_dump(mode="json")
    payload.update(update)
    with pytest.raises(ValidationError):
        FeatureResult.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "update",
    [
        {"support": "limited"},
        {"p_value": 0.0},
        {"adjusted_p_value": 0.5},
    ],
)
def test_abstained_result_cannot_carry_a_pooled_claim(update):
    payload = analyze_replication(request_for([None, None])).features[0].model_dump(mode="json")
    payload.update(update)
    with pytest.raises(ValidationError):
        FeatureResult.model_validate_json(json.dumps(payload))
