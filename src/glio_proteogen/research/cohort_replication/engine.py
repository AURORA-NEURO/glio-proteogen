"""Bounded deterministic meta-analysis of caller-owned aggregate effects."""

from __future__ import annotations

from math import erfc, fsum, sqrt

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .canonical import canonical_request_digest, require_byte_limit, result_payload_digest
from .contracts import (
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    CohortEffect,
    DirectionAgreement,
    FeatureRequest,
    FeatureResult,
    Heterogeneity,
    LeaveOneOut,
    MetaEstimate,
    PredictionInterval,
    ReplayResult,
    ReplicationRequest,
    ReplicationResult,
    require_finite,
)
from .profile import ASSUMPTIONS, algorithm_profile

NORMAL_975 = 1.959963984540054
_ZERO_DIGEST = "sha256:" + "0" * 64


def _estimate(values: tuple[float, ...], weights: tuple[float, ...]) -> MetaEstimate:
    total_weight = fsum(weights)
    mean = require_finite(
        fsum(value * weight for value, weight in zip(values, weights, strict=True)) / total_weight
    )
    se = require_finite(sqrt(1.0 / total_weight))
    return MetaEstimate(
        estimate=mean,
        standard_error=se,
        lower=mean - NORMAL_975 * se,
        upper=mean + NORMAL_975 * se,
        p_value=erfc(abs(mean) / se / sqrt(2.0)),
    )


def _pool(effects: tuple[CohortEffect, ...]) -> tuple[MetaEstimate, MetaEstimate, Heterogeneity]:
    values = tuple(float(effect.estimate) for effect in effects if effect.estimate is not None)
    variances = tuple(
        float(effect.standard_error) ** 2 for effect in effects if effect.standard_error is not None
    )
    weights = tuple(1.0 / variance for variance in variances)
    fixed = _estimate(values, weights)
    q = max(
        0.0,
        fsum(
            weight * (value - fixed.estimate) ** 2
            for value, weight in zip(values, weights, strict=True)
        ),
    )
    degrees = len(effects) - 1
    # The pairwise identity avoids cancellation when one inverse-variance weight dominates.
    prefix_weight = 0.0
    pair_products = []
    for weight in weights:
        pair_products.append(weight * prefix_weight)
        prefix_weight = fsum((prefix_weight, weight))
    c = 2.0 * fsum(pair_products) / fsum(weights)
    tau_squared = max(0.0, (q - degrees) / c)
    random = _estimate(values, tuple(1.0 / (variance + tau_squared) for variance in variances))
    heterogeneity = Heterogeneity(
        q=q,
        degrees_of_freedom=degrees,
        i_squared_percent=max(0.0, (q - degrees) / q) * 100.0 if q > 0 else 0.0,
        tau_squared=tau_squared,
    )
    return fixed, random, heterogeneity


def _direction(effects: tuple[CohortEffect, ...]) -> DirectionAgreement:
    positive = sum(effect.estimate is not None and effect.estimate > 0 for effect in effects)
    negative = sum(effect.estimate is not None and effect.estimate < 0 for effect in effects)
    zero = len(effects) - positive - negative
    classification = "direction_indeterminate"
    if positive and negative:
        classification = "mixed_directions"
    elif len(effects) >= 2 and all(
        effect.estimate is not None
        and effect.standard_error is not None
        and effect.estimate - NORMAL_975 * effect.standard_error > 0
        for effect in effects
    ):
        classification = "all_nominal_intervals_positive"
    elif len(effects) >= 2 and all(
        effect.estimate is not None
        and effect.standard_error is not None
        and effect.estimate + NORMAL_975 * effect.standard_error < 0
        for effect in effects
    ):
        classification = "all_nominal_intervals_negative"
    return DirectionAgreement(
        positive_count=positive,
        negative_count=negative,
        zero_count=zero,
        majority_fraction=max(positive, negative, zero) / len(effects) if effects else None,
        classification=classification,  # type: ignore[arg-type]
    )


def _feature(feature: FeatureRequest) -> FeatureResult:
    observed = tuple(effect for effect in feature.effects if effect.state == "observed")
    if len(observed) < 2:
        return FeatureResult(
            feature_id=feature.feature_id,
            label=feature.label,
            effects=feature.effects,
            observed_count=len(observed),
            total_count=len(feature.effects),
            direction_agreement=_direction(observed),
            support="abstained",
            fixed_effect=None,
            random_effect=None,
            heterogeneity=None,
            prediction_interval=None,
            p_value=None,
            adjusted_p_value=1.0,
            dependence_robust_adjusted_p_value=1.0,
            leave_one_out=(),
            reasons=(
                "Fewer than two observed independent cohorts; aggregate estimates are withheld.",
            ),
        )
    fixed, random, heterogeneity = _pool(observed)
    prediction: PredictionInterval | None = None
    leave_one_out: tuple[LeaveOneOut, ...] = ()
    if len(observed) >= 3:
        spread = NORMAL_975 * sqrt(heterogeneity.tau_squared + random.standard_error**2)
        prediction = PredictionInterval(
            lower=random.estimate - spread, upper=random.estimate + spread
        )
        leave_one_out = tuple(
            LeaveOneOut(
                omitted_cohort_id=effect.cohort_id,
                observed_count=len(observed) - 1,
                random_effect=remaining,
                delta_estimate=remaining.estimate - random.estimate,
            )
            for effect in observed
            for remaining in (
                _pool(tuple(other for other in observed if other.cohort_id != effect.cohort_id))[1],
            )
        )
    reasons = [
        "Caller-supplied aggregate effects permit exploratory pooling; support remains limited."
    ]
    if len(observed) < len(feature.effects):
        reasons.append(
            "Missing or unsupported cohorts are excluded without imputation and remain visible in coverage."
        )
    if len(observed) < 3:
        reasons.append(
            "Prediction interval and leave-one-cohort-out refits require at least three observed cohorts."
        )
    else:
        reasons.append(
            "Prediction and confidence intervals use nominal normal approximations, which are uncertain with few cohorts."
        )
    return FeatureResult(
        feature_id=feature.feature_id,
        label=feature.label,
        effects=feature.effects,
        observed_count=len(observed),
        total_count=len(feature.effects),
        direction_agreement=_direction(observed),
        support="limited",
        fixed_effect=fixed,
        random_effect=random,
        heterogeneity=heterogeneity,
        prediction_interval=prediction,
        p_value=random.p_value,
        adjusted_p_value=1.0,
        dependence_robust_adjusted_p_value=1.0,
        leave_one_out=leave_one_out,
        reasons=tuple(reasons),
    )


def _adjustments(features: tuple[FeatureResult, ...]) -> tuple[FeatureResult, ...]:
    family_size = len(features)
    ordered = sorted(
        range(family_size),
        key=lambda index: (
            features[index].p_value if features[index].p_value is not None else 1.0,
            features[index].feature_id,
        ),
    )
    adjusted = [1.0] * family_size
    previous = 1.0
    for rank_index in range(family_size - 1, -1, -1):
        index = ordered[rank_index]
        raw_p_value = features[index].p_value
        p_value = raw_p_value if raw_p_value is not None else 1.0
        previous = min(previous, p_value * family_size / (rank_index + 1), 1.0)
        adjusted[index] = previous
    harmonic = fsum(1.0 / rank for rank in range(1, family_size + 1))
    return tuple(
        feature.model_copy(
            update={
                "adjusted_p_value": adjusted[index],
                "dependence_robust_adjusted_p_value": min(1.0, harmonic * adjusted[index]),
            }
        )
        for index, feature in enumerate(features)
    )


def analyze_replication(request: ReplicationRequest) -> ReplicationResult:
    """Compute an exploratory receipt without accepting participant-level data."""

    request = ReplicationRequest.model_validate(request)
    require_byte_limit(request.model_dump(mode="json"), MAX_REQUEST_BYTES)
    profile = algorithm_profile()
    result = ReplicationResult(
        profile_digest=profile.profile_digest,
        analysis_id=request.analysis_id,
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        disease_context=request.disease_context,
        estimand_id=request.estimand_id,
        effect_scale=request.effect_scale,
        contrast=request.contrast,
        independence_basis=request.independence_basis,
        cohorts=request.cohorts,
        features=_adjustments(tuple(_feature(feature) for feature in request.features)),
        family_size=len(request.features),
        limitations=ASSUMPTIONS,
    )
    result = result.model_copy(update={"result_digest": result_payload_digest(result)})
    require_byte_limit(result.model_dump(mode="json"), MAX_RESULT_BYTES)
    return result


def verify_replay(request: ReplicationRequest, result: ReplicationResult) -> ReplayResult:
    """Recompute every numerical field; a self-rehashed mutation still fails."""

    expected = analyze_replication(request)
    valid = canonical_json_bytes(result.model_dump(mode="json")) == canonical_json_bytes(
        expected.model_dump(mode="json")
    )
    return ReplayResult(
        valid=valid, request_digest=expected.request_digest, result_digest=expected.result_digest
    )
