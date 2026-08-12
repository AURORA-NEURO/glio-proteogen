"""Compact public-contract boundaries for M02-04 quality computation."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from evals.m02_04.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m02_04 import (
    ComputeIdentificationQualityRequest,
    IdentificationMetricResult,
    IdentificationMetricStatus,
    IdentificationQualityDisposition,
    IdentificationQualityPolicy,
    IdentificationQualityProfile,
    MetricDirection,
    MetricObservation,
    MetricObservationState,
    MetricThreshold,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    observation_digest,
    policy_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    compute_identification_quality,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m02_04.schema import ContractName

pytestmark = pytest.mark.contract
ZERO = "sha256:" + ("0" * 64)
BAD = "sha256:" + ("f" * 64)


def _observation_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912
    observations = build_scenario_request().observations
    ratio = deepcopy(observations[0].model_dump(mode="python"))
    sample = deepcopy(observations[-1].model_dump(mode="python"))
    mass_error = deepcopy(observations[2].model_dump(mode="python"))
    if case == "duplicate_evidence":
        ratio["evidence"] = (ratio["evidence"][0], ratio["evidence"][0])
    elif case == "ratio_shape":
        ratio["numerator"] = None
    elif case == "proportion_domain":
        ratio["numerator"] = 101.0
    elif case == "sample_value":
        sample["value"] = 1.0
        return sample
    elif case == "sample_ratio":
        sample["numerator"], sample["denominator"] = 1.0, 1.0
        return sample
    elif case == "mass_value":
        mass_error["value"] = True
        return mass_error
    elif case == "mass_ratio":
        mass_error["numerator"], mass_error["denominator"] = 1.0, 1.0
        return mass_error
    elif case == "observed_bound":
        ratio["upper_bound"] = 1.0
    elif case in {"censored_bound", "censored_value"}:
        ratio.update(
            state=MetricObservationState.CENSORED,
            numerator=None,
            denominator=None,
            upper_bound=None if case == "censored_bound" else 1.0,
        )
        if case == "censored_value":
            ratio["value"] = 0.5
    elif case == "nonobserved_value":
        ratio.update(
            state=MetricObservationState.MISSING,
            numerator=None,
            denominator=None,
            value=0.5,
        )
    elif case == "nonfinite":
        mass_error["value"] = float("nan")
        return mass_error
    elif case == "zero_denominator":
        ratio["denominator"] = 0.0
    else:
        ratio["numerator"] = -1.0
    return ratio


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_evidence", "evidence must be unique"),
        ("ratio_shape", "requires numerator and denominator"),
        ("proportion_domain", "numerator cannot exceed denominator"),
        ("sample_value", "requires a boolean value"),
        ("sample_ratio", "cannot carry ratio inputs"),
        ("mass_value", "requires a numeric value"),
        ("mass_ratio", "cannot carry ratio inputs"),
        ("observed_bound", "cannot carry a censoring bound"),
        ("censored_bound", "requires an upper bound"),
        ("censored_value", "cannot carry observed inputs"),
        ("nonobserved_value", "nonobserved metric cannot carry values"),
        ("nonfinite", "finite number"),
        ("zero_denominator", "greater than 0"),
        ("negative_numerator", "greater than or equal to 0"),
    ],
)
def test_observation_state_shape_and_numeric_domain_are_closed(
    case: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        MetricObservation.model_validate(_observation_payload(case), strict=True)


def _threshold_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0911, PLR0912
    thresholds = build_scenario_request().policy.thresholds
    higher = deepcopy(thresholds[0].model_dump(mode="python"))
    lower = deepcopy(thresholds[1].model_dump(mode="python"))
    bounded = deepcopy(thresholds[4].model_dump(mode="python"))
    if case == "direction":
        higher["direction"] = MetricDirection.LOWER_IS_BETTER
    elif case == "higher_missing":
        higher["pass_minimum"] = None
    elif case == "lower_missing":
        lower["pass_maximum"] = None
        return lower
    elif case == "range_missing":
        bounded["pass_maximum"] = None
        return bounded
    elif case == "higher_max":
        higher["pass_maximum"] = 0.9
    elif case == "lower_min":
        lower["pass_minimum"] = 0.0
        return lower
    elif case == "warning_pair":
        bounded["warning_maximum"] = None
        return bounded
    elif case == "proportion_bound":
        higher["pass_minimum"] = 1.1
    elif case == "pass_range":
        bounded.update(pass_minimum=1.2, pass_maximum=1.1)
        return bounded
    elif case == "warning_range":
        bounded.update(warning_minimum=1.3, warning_maximum=1.2)
        return bounded
    elif case == "warning_minimum":
        bounded["warning_minimum"] = 0.9
        return bounded
    elif case == "warning_maximum":
        bounded.update(warning_minimum=0.0, warning_maximum=0.5)
        return bounded
    else:
        higher["pass_minimum"] = float("inf")
    return higher


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("direction", "direction contradicts"),
        ("higher_missing", "requires a pass minimum"),
        ("lower_missing", "requires a pass maximum"),
        ("range_missing", "requires pass minimum and maximum"),
        ("higher_max", "cannot carry maximum thresholds"),
        ("lower_min", "cannot carry minimum thresholds"),
        ("warning_pair", "must be supplied together"),
        ("proportion_bound", "within zero and one"),
        ("pass_range", "pass minimum cannot exceed maximum"),
        ("warning_range", "warning minimum cannot exceed maximum"),
        ("warning_minimum", "warning range must contain pass range"),
        ("warning_maximum", "warning range must contain pass range"),
        ("nonfinite", "finite number"),
    ],
)
def test_threshold_direction_bounds_and_warning_shape_are_closed(
    case: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        MetricThreshold.model_validate(_threshold_payload(case), strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("policy", "every identification quality metric exactly once"),
        ("observations", "one observation for every quality metric"),
        ("configuration", "does not bind the quality policy"),
        ("consent", "consent does not authorize"),
        ("identity", "identity lineage must be resolved"),
        ("quality", "every upstream control must accept"),
    ],
)
def test_policy_request_authority_and_configuration_are_closed(
    case: str,
    message: str,
) -> None:
    values = build_scenario_request().model_dump(mode="python")
    if case == "policy":
        thresholds = values["policy"]["thresholds"]
        values["policy"]["thresholds"] = (thresholds[0], *thresholds[:-1])
    elif case == "observations":
        observations = values["observations"]
        values["observations"] = (observations[0], *observations[:-1])
    elif case == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = BAD
    elif case == "consent":
        values["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    elif case == "identity":
        values["context"]["references"]["identity_lineage"][
            "state"
        ] = IdentityLineageState.UNRESOLVED
    else:
        values["context"]["references"]["quality"][
            "state"
        ] = UpstreamDecisionState.REJECTED

    model = (
        IdentificationQualityPolicy
        if case == "policy"
        else ComputeIdentificationQualityRequest
    )
    payload = values["policy"] if case == "policy" else values
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload, strict=True)


def test_request_policy_observation_and_evidence_order_is_semantic() -> None:
    request = build_scenario_request()
    values = request.model_dump(mode="python")
    values["policy"]["thresholds"] = tuple(reversed(values["policy"]["thresholds"]))
    values["observations"] = tuple(reversed(values["observations"]))
    policy = IdentificationQualityPolicy.model_validate(values["policy"], strict=True)
    values["context"]["references"]["approved_configuration"]["evidence"][
        "digest"
    ] = configuration_digest(policy)
    reordered = ComputeIdentificationQualityRequest.model_validate(values, strict=True)
    observation = request.observations[0].model_copy(
        update={
            "evidence": (
                request.observations[0].evidence[0],
                request.observations[1].evidence[0],
            )
        }
    )

    assert policy_digest(policy) == policy_digest(request.policy)
    assert canonical_request_digest(reordered) == canonical_request_digest(request)
    assert observation_digest(observation) == observation_digest(
        observation.model_copy(update={"evidence": tuple(reversed(observation.evidence))})
    )


def _metric_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912
    accepted = compute_identification_quality(build_scenario_request())
    metric = deepcopy(accepted.metrics[0].model_dump(mode="python"))
    if case in {"eval_unobserved", "observation_state"}:
        missing = compute_identification_quality(
            build_scenario_request("required_observation_missing")
        )
        metric = deepcopy(
            next(
                item
                for item in missing.metrics
                if item.status is IdentificationMetricStatus.NOT_EVALUABLE
            ).model_dump(mode="python")
        )
    if case == "duplicate_evidence":
        metric["evidence"] = (metric["evidence"][0], metric["evidence"][0])
    elif case == "not_eval_observed":
        metric["status"] = IdentificationMetricStatus.NOT_EVALUABLE
    elif case == "eval_unobserved":
        metric["status"] = IdentificationMetricStatus.PASS
    elif case == "unit":
        metric["unit"] = "ppm"
    elif case == "threshold_code":
        metric["threshold"] = accepted.metrics[1].threshold.model_dump(mode="python")
    elif case == "threshold_required":
        metric["required"] = False
    elif case == "observation_state":
        metric["state"] = MetricObservationState.CENSORED
    elif case == "evidence":
        metric["evidence"] = accepted.metrics[1].evidence
    elif case == "observation_digest":
        metric["provenance"]["observation_digest"] = BAD
    elif case == "threshold_digest":
        metric["provenance"]["threshold_digest"] = BAD
    elif case == "value":
        metric["value"] = 0.85
    else:
        metric["status"] = IdentificationMetricStatus.WARNING
    return metric


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_evidence", "result evidence must be unique"),
        ("not_eval_observed", "cannot carry an observed value"),
        ("eval_unobserved", "requires an observed value"),
        ("unit", "unit contradicts"),
        ("threshold_code", "contradicts its threshold"),
        ("threshold_required", "contradicts its threshold"),
        ("observation_state", "contradicts its observation"),
        ("evidence", "contradicts its observation"),
        ("observation_digest", "observation digest does not match"),
        ("threshold_digest", "threshold digest does not match"),
        ("value", "value contradicts"),
        ("status", "status contradicts"),
    ],
)
def test_metric_result_rejects_relational_forgery(case: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        IdentificationMetricResult.model_validate(_metric_payload(case), strict=True)


def _profile_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912
    profile = compute_identification_quality(build_scenario_request())
    values = deepcopy(profile.model_dump(mode="python"))
    values["result_digest"] = ZERO
    if case == "duplicate_metric":
        metrics = values["metrics"]
        values["metrics"] = (metrics[0], *metrics[:-1])
    elif case == "disposition":
        values["disposition"] = IdentificationQualityDisposition.QUARANTINED
    elif case == "support":
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
    elif case == "profile_id":
        values["quality_profile_id"] = "quality.m0204.forged"
    elif case == "provenance":
        values["provenance"]["module_id"] = "GLIO-PROTEOGEN-M99-99"
    elif case == "provenance_inputs":
        values["provenance"]["input_digests"] = tuple(
            item
            for item in values["provenance"]["input_digests"]
            if item != values["request_digest"]
        )
    elif case == "metric_provenance":
        values["metrics"][0]["provenance"]["assay_profile_digest"] = BAD
    elif case == "policy":
        values["policy_id"] = "policy.forged"
    elif case == "limitation":
        values["limitations"][0]["code"] = "forged_limitation"
    elif case == "duplicate_evidence":
        evidence = values["evidence"]
        values["evidence"] = (evidence[0], *evidence[:-1])
    elif case == "evidence_digest":
        values["evidence"][0]["reference"]["digest"] = BAD
    elif case == "configuration":
        configuration = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "approved_configuration"
        )
        old = configuration["evidence_digest"]
        configuration["evidence_digest"] = BAD
        values["provenance"]["input_digests"] = (
            *values["provenance"]["input_digests"],
            BAD,
        )
        control_evidence = next(
            item for item in values["evidence"] if item["reference"]["digest"] == old
        )
        control_evidence["reference"]["digest"] = BAD
    elif case == "control":
        quality = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "quality"
        )
        quality["state"] = "rejected"
    elif case == "consent":
        values["provenance"]["consent_decision_id"] = "decision.forged"
    elif case == "claim":
        values["evidence"][0]["claim"] = "Forged evidence claim."
    else:
        values["result_digest"] = BAD
    return values


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_metric", "every quality metric exactly once"),
        ("disposition", "disposition contradicts metric results"),
        ("support", "support contradicts disposition"),
        ("profile_id", "identifier does not bind request"),
        ("provenance", "provenance is inconsistent"),
        ("provenance_inputs", "provenance inputs are incomplete"),
        ("metric_provenance", "metric provenance contradicts profile digests"),
        ("policy", "thresholds do not bind its policy digest"),
        ("limitation", "requires both limitation codes"),
        ("duplicate_evidence", "profile evidence must be unique"),
        ("evidence_digest", "must contain exactly controls and assay profile"),
        ("configuration", "configuration evidence does not bind result"),
        ("control", "control states are inconsistent"),
        ("consent", "consent provenance contradicts"),
        ("claim", "evidence claims are inconsistent"),
        ("result_digest", "digest does not match content"),
    ],
)
def test_quality_profile_rejects_envelope_forgery(case: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        IdentificationQualityProfile.model_validate(_profile_payload(case), strict=True)


def test_all_public_schema_exports_are_versioned_strict_and_distinct() -> None:
    names: tuple[ContractName, ...] = (
        "request",
        "output",
        "assay_profile",
        "policy",
        "threshold",
        "observation",
        "metric",
    )
    schemas = [contract_json_schema(name) for name in names]

    assert {schema["$schema"] for schema in schemas} == {
        "https://json-schema.org/draft/2020-12/schema"
    }
    assert len({schema["$id"] for schema in schemas}) == len(names)
    assert all(
        schema["x-glio-contract"]
        == {
            "moduleId": "GLIO-PROTEOGEN-M02-04",
            "contractVersion": "1.0.0",
            "strict": True,
            "biologicalInterpretation": False,
        }
        for schema in schemas
    )
