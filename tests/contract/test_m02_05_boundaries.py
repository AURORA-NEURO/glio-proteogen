"""Compact relational and forgery boundaries for M02-05."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from evals.m02_05.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m02_05 import (
    M0205_MAX_FLAGS,
    M0205_MAX_RULES,
    M0205_MAX_SIGNALS,
    ArtifactClass,
    ArtifactRule,
    Comparison,
    DetectIdentificationArtifactsRequest,
    DetectionDisposition,
    FlagDisposition,
    IdentificationArtifactDetectionResult,
    IdentificationArtifactFlag,
    IdentificationArtifactPolicy,
    IdentificationArtifactProfile,
    IdentificationSignalObservation,
    IdentificationSignalState,
    PosteriorState,
    RuleEvaluationTrace,
    canonical_request_digest,
    configuration_digest,
    policy_digest,
    rule_digest,
    signal_summary_digest_from_values,
)
from glio_proteogen.contracts.m02_05 import v1 as m0205_v1
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    detect_identification_artifacts,
)

pytestmark = pytest.mark.contract
ZERO = "sha256:" + ("0" * 64)
BAD = "sha256:" + ("f" * 64)
TRIGGERED_POSTERIOR = 0.95


def _bind_configuration(values: dict[str, Any]) -> None:
    profile = IdentificationArtifactProfile.model_validate(
        values["detector_profile"],
        strict=True,
    )
    policy = IdentificationArtifactPolicy.model_validate(values["policy"], strict=True)
    rules = tuple(ArtifactRule.model_validate(item, strict=True) for item in values["rules"])
    values["context"]["references"]["approved_configuration"]["evidence"][
        "digest"
    ] = configuration_digest(profile, policy, rules)


def _bind_result_policy(values: dict[str, Any]) -> None:
    policy = IdentificationArtifactPolicy(
        policy_id=values["policy_id"],
        version=values["policy_version"],
        review_threshold=values["review_threshold"],
        exclusion_threshold=values["exclusion_threshold"],
        enabled_classes=values["enabled_classes"],
        max_rules=values["max_rules"],
        max_signals=values["max_signals"],
        max_flags=values["max_flags"],
        max_evaluations=values["max_evaluations"],
    )
    values["policy_digest"] = policy_digest(policy)


def _trace_payload() -> dict[str, Any]:
    result = detect_identification_artifacts(build_scenario_request())
    return deepcopy(result.flags[0].evaluations[0].model_dump(mode="python"))


def _bind_trace_signal(values: dict[str, Any]) -> None:
    state = values["signal_state"]
    state_value = state.value if isinstance(state, IdentificationSignalState) else state
    values["signal_digest"] = signal_summary_digest_from_values(
        (
            values["target_id"],
            values["signal_id"],
            state_value,
            values["signal_value"],
            values["signal_unit"],
        ),
        values["evidence_digests"],
    )


def _flag_payload() -> dict[str, Any]:
    result = detect_identification_artifacts(build_scenario_request())
    return deepcopy(result.flags[0].model_dump(mode="python"))


def _replace_trace_rule(values: dict[str, Any], rule: ArtifactRule) -> None:
    values.update(
        rule_id=rule.rule_id,
        artifact_class=rule.artifact_class,
        signal_id=rule.signal_id,
        rule_digest=rule_digest(rule),
        rule=rule,
        posterior_if_triggered=rule.posterior_if_triggered,
        posterior_if_clear=rule.posterior_if_clear,
        required_signal=rule.required_signal,
        exclusion_eligible=rule.exclusion_eligible,
    )


@pytest.mark.parametrize(
    ("subject", "case", "message"),
    [
        ("profile", "duplicate_rules", "rule identifiers must be unique"),
        ("policy", "duplicate_classes", "classes must be unique"),
        ("policy", "threshold_order", "review threshold must be below"),
        ("policy", "zero_rule_cap", "greater than 0"),
        ("policy", "signal_cap", "less than or equal"),
        ("policy", "flag_cap", "less than or equal"),
    ],
)
def test_profile_policy_uniqueness_thresholds_and_caps_are_closed(
    subject: str,
    case: str,
    message: str,
) -> None:
    request = build_scenario_request()
    model: type[IdentificationArtifactProfile | IdentificationArtifactPolicy]
    if subject == "profile":
        values = request.detector_profile.model_dump(mode="python")
        values["required_rule_ids"] = (
            values["required_rule_ids"][0],
            *values["required_rule_ids"],
        )
        model = IdentificationArtifactProfile
    else:
        values = request.policy.model_dump(mode="python")
        if case == "duplicate_classes":
            values["enabled_classes"] = (
                values["enabled_classes"][0],
                *values["enabled_classes"][:-1],
            )
        elif case == "threshold_order":
            values["review_threshold"] = values["exclusion_threshold"]
        elif case == "zero_rule_cap":
            values["max_rules"] = 0
        elif case == "signal_cap":
            values["max_signals"] = M0205_MAX_SIGNALS + 1
        else:
            values["max_flags"] = M0205_MAX_FLAGS + 1
        model = IdentificationArtifactPolicy

    with pytest.raises(ValidationError, match=message):
        model.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("observed_without_value", "observed identification signal requires a value"),
        ("nonobserved_value", "non-observed identification signal cannot carry a value"),
        ("nonobserved_unit", "non-observed identification signal cannot carry a unit"),
        ("duplicate_evidence", "evidence references must be unique"),
        ("duplicate_evidence_digest", "evidence digests must be unique"),
        ("nonfinite", "finite number"),
        ("invalid_unit", "String should match pattern"),
    ],
)
def test_signal_state_value_unit_and_evidence_are_closed(case: str, message: str) -> None:
    values = build_scenario_request().signals[0].model_dump(mode="python")
    if case == "observed_without_value":
        values["value"] = None
    elif case == "nonobserved_value":
        values.update(state=IdentificationSignalState.MISSING, value=0.1, unit=None)
    elif case == "nonobserved_unit":
        values.update(state=IdentificationSignalState.UNSUPPORTED, value=None, unit="fraction")
    elif case == "duplicate_evidence":
        values["evidence"] = (values["evidence"][0], values["evidence"][0])
    elif case == "duplicate_evidence_digest":
        alias = deepcopy(values["evidence"][0])
        alias["artifact_id"] = f"{alias['artifact_id']}.alias"
        values["evidence"] = (values["evidence"][0], alias)
    elif case == "nonfinite":
        values["value"] = float("nan")
    else:
        values["unit"] = "not a unit"

    with pytest.raises(ValidationError, match=message):
        IdentificationSignalObservation.model_validate(values, strict=True)


def _request_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912
    values = build_scenario_request().model_dump(mode="python")
    if case == "duplicate_rule":
        values["rules"] = (values["rules"][0], *values["rules"])
    elif case == "duplicate_signal":
        values["signals"] = (*values["signals"], values["signals"][0])
    elif case == "rule_cap":
        values["policy"]["max_rules"] = len(values["rules"]) - 1
    elif case == "undefined_profile_rule":
        values["detector_profile"]["required_rule_ids"] = (
            *values["detector_profile"]["required_rule_ids"],
            "rule.m0205.undefined",
        )
    elif case == "disabled_class":
        values["policy"]["enabled_classes"] = tuple(ArtifactClass)[:-1]
    elif case == "clear_posterior":
        values["rules"][0]["posterior_if_clear"] = values["policy"]["review_threshold"]
    elif case == "unknown_signal":
        values["rules"][0]["signal_id"] = "signal.m0205.undefined"
    elif case == "unconfigured_signal":
        signal = deepcopy(values["signals"][0])
        signal["signal_id"] = "signal.m0205.unconfigured"
        values["signals"] = (*values["signals"], signal)
    elif case == "numeric_unit":
        values["signals"][0]["unit"] = "percent"
    elif case == "boolean_shape":
        values["rules"][0].update(
            comparison=Comparison.BOOLEAN_EQUAL,
            threshold=None,
            expected_bool=True,
            unit=None,
        )
    elif case == "flag_cap":
        values["policy"]["max_flags"] = len(ArtifactClass) - 1
    elif case == "evaluation_cap":
        values["policy"]["max_evaluations"] = len(values["rules"]) - 1
    elif case == "colliding_top_evidence":
        values["detector_profile"]["evidence"]["digest"] = values["context"][
            "references"
        ]["quality"]["evidence"]["digest"]
    elif case == "flag_evidence_cap":
        reference = values["signals"][0]["evidence"][0]
        values["signals"][0]["evidence"] = tuple(
            {
                **reference,
                "artifact_id": f"artifact.synthetic.m0205.capacity.{index:02d}",
                "digest": f"sha256:{index + 1:064x}",
            }
            for index in range(64)
        )
    elif case == "consent":
        values["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    elif case == "identity":
        values["context"]["references"]["identity_lineage"][
            "state"
        ] = IdentityLineageState.UNRESOLVED
    elif case == "quality":
        values["context"]["references"]["quality"][
            "state"
        ] = UpstreamDecisionState.REJECTED
    _bind_configuration(values)
    if case == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = BAD
    return cast("dict[str, Any]", values)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_rule", "rule identifiers must be unique"),
        ("duplicate_signal", "target/identifier pairs must be unique"),
        ("rule_cap", "exceeds the active policy"),
        ("undefined_profile_rule", "references an undefined rule"),
        ("disabled_class", "rule class is disabled"),
        ("clear_posterior", "clear configured posterior must remain below"),
        ("unknown_signal", "rule references an unknown signal"),
        ("unconfigured_signal", "signal is not covered by the active rules"),
        ("numeric_unit", "numeric identification signal unit must match"),
        ("boolean_shape", "boolean identification signals must be unitless booleans"),
        ("flag_cap", "exceeds the result flag limit"),
        ("evaluation_cap", "exceeds evaluation trace capacity"),
        ("colliding_top_evidence", "evidence digests must be distinct"),
        ("flag_evidence_cap", "flag evidence exceeds output capacity"),
        ("configuration", "does not bind identification detector"),
        ("consent", "consent does not authorize"),
        ("identity", "identity lineage must be resolved"),
        ("quality", "every upstream control must accept"),
    ],
)
def test_request_authority_configuration_rules_signals_and_caps_are_closed(
    case: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        DetectIdentificationArtifactsRequest.model_validate(
            _request_payload(case),
            strict=True,
        )


def test_request_provenance_capacity_is_checked_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = build_scenario_request().model_dump(mode="python")
    monkeypatch.setattr(m0205_v1, "M0205_MAX_PROVENANCE_INPUTS", 10)

    with pytest.raises(ValidationError, match="exceeds provenance capacity"):
        DetectIdentificationArtifactsRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    "field",
    [
        "rule_id",
        "artifact_class",
        "signal_id",
        "rule_digest",
        "posterior_if_triggered",
        "posterior_if_clear",
        "required_signal",
        "exclusion_eligible",
    ],
)
def test_rule_trace_rejects_every_exact_rule_manifest_mismatch(field: str) -> None:
    values = _trace_payload()
    replacements: dict[str, object] = {
        "rule_id": "rule.m0205.forged",
        "artifact_class": (
            ArtifactClass.CONTAMINATION
            if values["artifact_class"] is not ArtifactClass.CONTAMINATION
            else ArtifactClass.TECHNICAL
        ),
        "signal_id": "signal.m0205.forged",
        "rule_digest": BAD,
        "posterior_if_triggered": values["posterior_if_triggered"] - 0.01,
        "posterior_if_clear": values["posterior_if_clear"] + 0.01,
        "required_signal": not values["required_signal"],
        "exclusion_eligible": not values["exclusion_eligible"],
    }
    values[field] = replacements[field]

    with pytest.raises(ValidationError, match="contradicts its exact rule"):
        RuleEvaluationTrace.model_validate(values, strict=True)


def _invalid_trace_payload(case: str) -> dict[str, Any]:  # noqa: C901
    values = _trace_payload()
    if case == "duplicate_evidence":
        values["evidence_digests"] = (
            values["evidence_digests"][0],
            values["evidence_digests"][0],
        )
    elif case == "missing_digest":
        values["signal_digest"] = None
    elif case == "missing_state":
        values["signal_state"] = None
    elif case == "missing_evidence":
        values["evidence_digests"] = ()
    elif case == "triggered_nonobserved":
        values.update(
            signal_state=IdentificationSignalState.MISSING,
            signal_value=None,
            signal_unit=None,
            triggered=True,
        )
        _bind_trace_signal(values)
    elif case == "observed_without_value":
        values["signal_value"] = None
    elif case in {"boolean_value", "boolean_unit"}:
        rule_values = deepcopy(values["rule"])
        rule_values.update(
            comparison=Comparison.BOOLEAN_EQUAL,
            threshold=None,
            upper_threshold=None,
            expected_bool=True,
            unit=None,
        )
        _replace_trace_rule(values, ArtifactRule.model_validate(rule_values, strict=True))
        values["signal_value"] = 1.0 if case == "boolean_value" else True
        values["signal_unit"] = None if case == "boolean_value" else "fraction"
    elif case == "numeric_bool":
        values["signal_value"] = True
    elif case == "numeric_unit":
        values["signal_unit"] = "percent"
    elif case == "nonobserved_payload":
        values["signal_state"] = IdentificationSignalState.MISSING
    elif case == "signal_digest":
        values["signal_digest"] = BAD
    elif case == "trigger":
        values["triggered"] = True
    return values


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_evidence", "evidence digests must be unique"),
        ("missing_digest", "signal trace must be all present or all absent"),
        ("missing_state", "signal trace must be all present or all absent"),
        ("missing_evidence", "signal trace must be all present or all absent"),
        ("triggered_nonobserved", "only an observed signal can trigger"),
        ("observed_without_value", "observed rule trace requires a signal value"),
        ("boolean_value", "boolean rule trace requires a unitless boolean"),
        ("boolean_unit", "boolean rule trace requires a unitless boolean"),
        ("numeric_bool", "numeric rule trace unit contradicts its rule"),
        ("numeric_unit", "numeric rule trace unit contradicts its rule"),
        ("nonobserved_payload", "non-observed rule trace cannot carry"),
        ("signal_digest", "signal digest contradicts its aggregate summary"),
        ("trigger", "trigger contradicts rule and aggregate signal"),
    ],
)
def test_rule_trace_signal_trigger_and_posterior_relations_are_closed(
    case: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        RuleEvaluationTrace.model_validate(_invalid_trace_payload(case), strict=True)


def test_trace_defensively_rejects_impossible_nested_posterior_order() -> None:
    values = _trace_payload()
    rule_values = deepcopy(values["rule"])
    rule_values.update(posterior_if_triggered=0.1, posterior_if_clear=0.2)
    invalid_rule = ArtifactRule.model_construct(**rule_values)
    _replace_trace_rule(values, invalid_rule)
    trace = RuleEvaluationTrace.model_construct(**values)

    with pytest.raises(ValueError, match="triggered posterior cannot be below clear posterior"):
        trace.trace_is_closed()


def test_boolean_rule_trace_accepts_exact_unitless_boolean_summary() -> None:
    values = _trace_payload()
    rule_values = deepcopy(values["rule"])
    rule_values.update(
        comparison=Comparison.BOOLEAN_EQUAL,
        threshold=None,
        upper_threshold=None,
        expected_bool=True,
        unit=None,
    )
    _replace_trace_rule(values, ArtifactRule.model_validate(rule_values, strict=True))
    values.update(signal_value=True, signal_unit=None, triggered=True)
    _bind_trace_signal(values)

    trace = RuleEvaluationTrace.model_validate(values, strict=True)

    assert trace.triggered is True


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("rules", "rules contradict evaluation traces"),
        ("class", "class contradicts evaluation traces"),
        ("target", "target contradicts evaluation traces"),
        ("evaluation_duplicate", "evaluation traces must be unique"),
        ("evidence_duplicate", "flag evidence must be unique"),
        ("evidence_digest", "flag evidence digests must be unique"),
        ("provenance", "provenance contradicts evaluation traces"),
        ("evidence_coverage", "evidence does not cover its signal traces"),
        ("posterior", "posterior state contradicts its disposition"),
    ],
)
def test_flag_rejects_rule_target_class_evidence_and_posterior_forgery(
    case: str,
    message: str,
) -> None:
    values = _flag_payload()
    if case == "rules":
        values["rule_ids"] = ("rule.m0205.forged",)
    elif case == "class":
        values["artifact_class"] = (
            ArtifactClass.CONTAMINATION
            if values["artifact_class"] is not ArtifactClass.CONTAMINATION
            else ArtifactClass.TECHNICAL
        )
    elif case == "target":
        values["target_id"] = "target.forged"
    elif case == "evaluation_duplicate":
        values["evaluations"] = (*values["evaluations"], values["evaluations"][0])
    elif case == "evidence_duplicate":
        values["evidence"] = (*values["evidence"], values["evidence"][0])
    elif case == "evidence_digest":
        alias = deepcopy(values["evidence"][0])
        alias["artifact_id"] = f"{alias['artifact_id']}.alias"
        values["evidence"] = (*values["evidence"], alias)
    elif case == "provenance":
        values["provenance"]["rule_digests"] = (BAD,)
    elif case == "evidence_coverage":
        traced = {
            digest
            for trace in values["evaluations"]
            for digest in trace["evidence_digests"]
        }
        values["evidence"] = tuple(
            item for item in values["evidence"] if item["digest"] not in traced
        )
    else:
        values["disposition"] = FlagDisposition.NOT_EVALUABLE

    with pytest.raises(ValidationError, match=message):
        IdentificationArtifactFlag.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "expected_count"),
    [
        ("unsupported", 1),
        ("zero_observed", len(ArtifactClass)),
    ],
)
def test_optional_unsupported_and_zero_observed_are_not_evaluable(
    case: str,
    expected_count: int,
) -> None:
    if case == "unsupported":
        request = build_scenario_request("unsupported_ood")
    else:
        values = build_scenario_request().model_dump(mode="python")
        for rule in values["rules"]:
            rule["required_signal"] = False
        for signal in values["signals"]:
            signal.update(
                state=IdentificationSignalState.MISSING,
                value=None,
                unit=None,
            )
        _bind_configuration(values)
        request = DetectIdentificationArtifactsRequest.model_validate(values, strict=True)

    result = detect_identification_artifacts(request)
    not_evaluable = [
        flag for flag in result.flags if flag.disposition is FlagDisposition.NOT_EVALUABLE
    ]

    assert len(not_evaluable) == expected_count
    assert all(flag.posterior.state is PosteriorState.NOT_EVALUABLE for flag in not_evaluable)
    assert result.disposition is DetectionDisposition.QUARANTINED
    assert result.exclusion_mask.excluded_target_ids == ()
    assert result.exclusion_mask.review_target_ids


@pytest.mark.parametrize(
    ("ineligible_posterior", "expected"),
    [(0.90, FlagDisposition.EXCLUDE), (0.95, FlagDisposition.REVIEW)],
)
def test_only_maximum_posterior_sources_control_exclusion_eligibility(
    ineligible_posterior: float,
    expected: FlagDisposition,
) -> None:
    values = build_scenario_request().model_dump(mode="python")
    technical = next(
        item for item in values["rules"] if item["artifact_class"] is ArtifactClass.TECHNICAL
    )
    eligible = deepcopy(technical)
    eligible.update(rule_id="rule.m0205.technical.eligible", exclusion_eligible=True)
    ineligible = deepcopy(technical)
    ineligible.update(
        rule_id="rule.m0205.technical.ineligible",
        posterior_if_triggered=ineligible_posterior,
        exclusion_eligible=False,
    )
    values["rules"] = tuple(
        (eligible, ineligible)
        if item["artifact_class"] is ArtifactClass.TECHNICAL
        else (item,)
        for item in values["rules"]
    )
    values["rules"] = tuple(item for group in values["rules"] for item in group)
    values["detector_profile"]["required_rule_ids"] = tuple(
        item["rule_id"] for item in values["rules"]
    )
    technical_signal = next(
        item
        for item in values["signals"]
        if item["signal_id"] == eligible["signal_id"]
    )
    technical_signal["value"] = 0.95
    _bind_configuration(values)
    request = DetectIdentificationArtifactsRequest.model_validate(values, strict=True)

    result = detect_identification_artifacts(request)
    flag = next(
        item for item in result.flags if item.artifact_class is ArtifactClass.TECHNICAL
    )

    assert flag.posterior.value == TRIGGERED_POSTERIOR
    assert flag.disposition is expected
    assert (flag.target_id in result.exclusion_mask.excluded_target_ids) is (
        expected is FlagDisposition.EXCLUDE
    )


def _policy_manifest_digest(
    result: IdentificationArtifactDetectionResult,
    **updates: object,
) -> str:
    values: dict[str, object] = {
        "policy_id": result.policy_id,
        "version": result.policy_version,
        "review_threshold": result.review_threshold,
        "exclusion_threshold": result.exclusion_threshold,
        "enabled_classes": result.enabled_classes,
        "max_rules": result.max_rules,
        "max_signals": result.max_signals,
        "max_flags": result.max_flags,
        "max_evaluations": result.max_evaluations,
    }
    values.update(updates)
    return policy_digest(IdentificationArtifactPolicy.model_validate(values, strict=True))


def _relational_result(  # noqa: C901, PLR0911, PLR0912
    case: str,
) -> IdentificationArtifactDetectionResult:
    result = detect_identification_artifacts(
        build_scenario_request("order_determinism" if case == "complete_rules" else "multi_class")
    )
    if case == "required_unique":
        return result.model_copy(
            update={"required_rule_ids": (result.required_rule_ids[0],) * 2}
        )
    if case == "classes_unique":
        return result.model_copy(update={"enabled_classes": (result.enabled_classes[0],) * 2})
    if case == "targets_unique":
        return result.model_copy(
            update={"evaluated_target_ids": (result.evaluated_target_ids[0],) * 2}
        )
    if case == "flags_unique":
        return result.model_copy(update={"flags": (*result.flags, result.flags[0])})
    if case == "thresholds":
        return result.model_copy(update={"review_threshold": result.exclusion_threshold})
    if case == "policy_digest":
        return result.model_copy(update={"policy_digest": BAD})
    if case in {"signal_reuse", "rule_reuse"}:
        source = result.flags[0].evaluations[0]
        victim = result.flags[1]
        trace = victim.evaluations[0].model_copy(
            update={
                "signal_id" if case == "signal_reuse" else "rule_id": (
                    source.signal_id if case == "signal_reuse" else source.rule_id
                )
            }
        )
        flags = list(result.flags)
        flags[1] = victim.model_copy(update={"evaluations": (trace,)})
        return result.model_copy(update={"flags": tuple(flags)})
    if case == "complete_rules":
        first_class = result.flags[0].artifact_class
        indexes = [
            index
            for index, flag in enumerate(result.flags)
            if flag.artifact_class is first_class
        ]
        flags = list(result.flags)
        flags[indexes[1]] = flags[indexes[1]].model_copy(update={"evaluations": ()})
        return result.model_copy(update={"flags": tuple(flags)})
    if case == "required_rule":
        return result.model_copy(update={"required_rule_ids": ("rule.m0205.undefined",)})
    if case == "rule_policy":
        review = 0.005
        return result.model_copy(
            update={
                "review_threshold": review,
                "policy_digest": _policy_manifest_digest(result, review_threshold=review),
            }
        )
    if case == "flag_coverage":
        return result.model_copy(
            update={"evaluated_target_ids": (*result.evaluated_target_ids, "target.omitted")}
        )
    if case == "flag_capacity":
        maximum = len(result.flags) - 1
        return result.model_copy(
            update={
                "max_flags": maximum,
                "policy_digest": _policy_manifest_digest(result, max_flags=maximum),
            }
        )
    if case == "evaluation_capacity":
        maximum = sum(len(flag.evaluations) for flag in result.flags) - 1
        return result.model_copy(
            update={
                "max_evaluations": maximum,
                "policy_digest": _policy_manifest_digest(result, max_evaluations=maximum),
            }
        )
    if case == "configuration":
        return result.model_copy(update={"configuration_digest": BAD})
    flag = result.flags[0]
    posterior = flag.posterior.model_copy(update={"value": 0.49})
    flags = (flag.model_copy(update={"posterior": posterior}), *result.flags[1:])
    return result.model_copy(update={"flags": flags})


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("required_unique", "required rule identifiers must be unique"),
        ("classes_unique", "enabled artifact classes must be unique"),
        ("targets_unique", "evaluated target identifiers must be unique"),
        ("flags_unique", "flags must be unique"),
        ("thresholds", "result thresholds are not ordered"),
        ("policy_digest", "policy manifest does not match its digest"),
        ("signal_reuse", "reused signal traces must carry one identical summary"),
        ("rule_reuse", "reused rule identifiers must carry one exact rule"),
        ("complete_rules", "class flag must evaluate the complete configured rule set"),
        ("required_rule", "omits a required detector rule"),
        ("rule_policy", "rules contradict the active policy"),
        ("flag_coverage", "flags do not cover every evaluated target and class"),
        ("flag_capacity", "exceeds its flag capacity"),
        ("evaluation_capacity", "exceeds its evaluation trace capacity"),
        ("configuration", "configuration manifest is inconsistent"),
        ("posterior", "flag contradicts result thresholds"),
    ],
)
def test_result_manifest_rejects_cross_trace_policy_shape_and_capacity_forgery(
    case: str,
    message: str,
) -> None:
    forged = _relational_result(case)

    with pytest.raises(ValueError, match=message):
        forged.result_is_relationally_closed()


def _forged_result(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912
    result = detect_identification_artifacts(build_scenario_request("multi_class"))
    values = deepcopy(result.model_dump(mode="python"))
    values["result_digest"] = ZERO
    excluded_flag = next(
        item for item in values["flags"] if item["disposition"] is FlagDisposition.EXCLUDE
    )
    if case == "trace":
        triggered = next(item for item in excluded_flag["evaluations"] if item["triggered"])
        triggered["triggered"] = False
    elif case == "trace_provenance":
        excluded_flag["evaluations"][0]["rule_digest"] = BAD
    elif case == "flag_provenance":
        excluded_flag["provenance"]["configuration_digest"] = BAD
    elif case == "provenance_inputs":
        values["provenance"]["input_digests"] = tuple(
            item
            for item in values["provenance"]["input_digests"]
            if item != values["request_digest"]
        )
    elif case == "provenance_module":
        values["provenance"]["module_id"] = "GLIO-PROTEOGEN-M99-99"
    elif case == "control":
        values["provenance"]["control_decisions"][0]["state"] = "rejected"
    elif case == "consent":
        values["provenance"]["consent_decision_id"] = "decision.forged"
    elif case == "approved_configuration":
        control = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "approved_configuration"
        )
        control["evidence_digest"] = BAD
        values["provenance"]["input_digests"] = (
            *values["provenance"]["input_digests"],
            BAD,
        )
    elif case == "mask":
        values["exclusion_mask"]["excluded_target_ids"] = ()
    elif case == "disposition":
        values["disposition"] = DetectionDisposition.ACCEPTED
    elif case == "support":
        values["support"]["status"] = SupportStatus.LIMITED
    elif case == "evidence_duplicate":
        evidence = values["evidence"]
        values["evidence"] = (evidence[0], *evidence[:-1])
    elif case == "evidence_digest_duplicate":
        alias = deepcopy(values["evidence"][0])
        alias["reference"]["artifact_id"] = f"{alias['reference']['artifact_id']}.alias"
        values["evidence"] = (values["evidence"][0], alias, *values["evidence"][2:])
    elif case == "evidence_index":
        values["evidence"][0]["reference"]["digest"] = BAD
    elif case == "profile_manifest":
        values["profile_id"] = "profile.m0205.forged"
    elif case == "evidence_claim":
        values["evidence"][0]["claim"] = "Forged evidence claim."
    elif case == "limitation":
        values["limitations"][0]["code"] = "forged_limitation"
    else:
        values["result_digest"] = BAD
    return cast("dict[str, Any]", values)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("trace", "rule trace trigger contradicts rule and aggregate signal"),
        ("trace_provenance", "rule evaluation trace contradicts its exact rule"),
        ("flag_provenance", "uses a different configuration"),
        ("provenance_inputs", "provenance inputs are incomplete"),
        ("provenance_module", "provenance is inconsistent"),
        ("control", "control states are inconsistent"),
        ("consent", "consent provenance is inconsistent"),
        ("approved_configuration", "approved configuration does not bind result"),
        ("mask", "exclusion mask contradicts flags"),
        ("disposition", "disposition contradicts flags"),
        ("support", "support contradicts disposition"),
        ("evidence_duplicate", "evidence must be unique"),
        ("evidence_digest_duplicate", "evidence digests must be unique"),
        ("evidence_index", "evidence index is inconsistent"),
        ("profile_manifest", "profile manifest does not match its digest"),
        ("evidence_claim", "evidence claims are inconsistent"),
        ("limitation", "requires both limitations"),
        ("digest", "digest does not match content"),
    ],
)
def test_result_rejects_trace_envelope_and_digest_forgery(
    case: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        IdentificationArtifactDetectionResult.model_validate(
            _forged_result(case),
            strict=True,
        )


def test_semantic_request_reordering_produces_identical_full_output() -> None:
    request = build_scenario_request("order_determinism")
    values = request.model_dump(mode="python")
    values["detector_profile"]["required_rule_ids"] = tuple(
        reversed(values["detector_profile"]["required_rule_ids"])
    )
    values["rules"] = tuple(reversed(values["rules"]))
    for signal in values["signals"]:
        signal["evidence"] = tuple(reversed(signal["evidence"]))
    values["signals"] = tuple(reversed(values["signals"]))
    reordered = DetectIdentificationArtifactsRequest.model_validate(values, strict=True)

    baseline = detect_identification_artifacts(request)
    replay = detect_identification_artifacts(reordered)

    assert canonical_request_digest(request) == canonical_request_digest(reordered)
    assert baseline == replay
    assert baseline.model_dump_json() == replay.model_dump_json()


def _comparison_rule(comparison: Comparison) -> ArtifactRule:
    values = build_scenario_request().rules[0].model_dump(mode="python")
    values.update(comparison=comparison, threshold=0.8, upper_threshold=None, expected_bool=None)
    if comparison is Comparison.BOOLEAN_EQUAL:
        values.update(threshold=None, expected_bool=True, unit=None)
    elif comparison in {Comparison.WITHIN_RANGE, Comparison.OUTSIDE_RANGE}:
        values["upper_threshold"] = 1.0
    return ArtifactRule.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("comparison", "state", "value", "expected"),
    [
        (Comparison.GREATER_THAN_OR_EQUAL, IdentificationSignalState.MISSING, 0.9, False),
        (Comparison.BOOLEAN_EQUAL, IdentificationSignalState.OBSERVED, True, True),
        (Comparison.BOOLEAN_EQUAL, IdentificationSignalState.OBSERVED, False, False),
        (Comparison.GREATER_THAN_OR_EQUAL, IdentificationSignalState.OBSERVED, True, False),
        (Comparison.GREATER_THAN_OR_EQUAL, IdentificationSignalState.OBSERVED, 0.8, True),
        (Comparison.LESS_THAN_OR_EQUAL, IdentificationSignalState.OBSERVED, 0.8, True),
        (Comparison.WITHIN_RANGE, IdentificationSignalState.OBSERVED, 0.9, True),
        (Comparison.WITHIN_RANGE, IdentificationSignalState.OBSERVED, 1.1, False),
        (Comparison.OUTSIDE_RANGE, IdentificationSignalState.OBSERVED, 1.1, True),
        (Comparison.OUTSIDE_RANGE, IdentificationSignalState.OBSERVED, 0.9, False),
    ],
)
def test_closed_comparison_union_is_evaluated_exactly(
    comparison: Comparison,
    state: IdentificationSignalState,
    *,
    value: float | bool,
    expected: bool,
) -> None:
    assert m0205_v1._rule_triggered(
        _comparison_rule(comparison),
        state,
        value=value,
    ) is expected


def test_defensive_comparison_and_present_state_guards_are_closed() -> None:
    rule = _comparison_rule(Comparison.WITHIN_RANGE).model_copy(
        update={"upper_threshold": None}
    )

    assert (
        m0205_v1._rule_triggered(
            rule,
            IdentificationSignalState.OBSERVED,
            value=0.9,
        )
        is False
    )
    with pytest.raises(ValueError, match="signal trace requires a state"):
        m0205_v1._present_signal_state(None)


def test_sparse_per_target_signal_matrix_remains_explicitly_not_evaluable() -> None:
    values = build_scenario_request("order_determinism").model_dump(mode="python")
    omitted = values["signals"][0]
    values["signals"] = tuple(
        item
        for item in values["signals"]
        if not (
            item["target_id"] == omitted["target_id"]
            and item["signal_id"] == omitted["signal_id"]
        )
    )
    request = DetectIdentificationArtifactsRequest.model_validate(values, strict=True)

    result = detect_identification_artifacts(request)
    flag = next(
        item
        for item in result.flags
        if item.target_id == omitted["target_id"]
        and any(trace.signal_id == omitted["signal_id"] for trace in item.evaluations)
    )

    assert flag.disposition is FlagDisposition.NOT_EVALUABLE


def test_maximum_signal_and_flag_request_shape_is_representable() -> None:
    base = build_scenario_request()
    rule = next(item for item in base.rules if item.artifact_class is ArtifactClass.TECHNICAL)
    maximum_signals = M0205_MAX_SIGNALS
    policy = IdentificationArtifactPolicy(
        policy_id=base.policy.policy_id,
        version=base.policy.version,
        review_threshold=base.policy.review_threshold,
        exclusion_threshold=base.policy.exclusion_threshold,
        enabled_classes=(ArtifactClass.TECHNICAL,),
        max_rules=1,
        max_signals=maximum_signals,
        max_flags=maximum_signals,
    )
    profile = base.detector_profile.model_copy(update={"required_rule_ids": (rule.rule_id,)})
    active_configuration = configuration_digest(profile, policy, (rule,))
    approved = base.context.references.approved_configuration.model_copy(
        update={
            "evidence": base.context.references.approved_configuration.evidence.model_copy(
                update={"digest": active_configuration}
            )
        }
    )
    context = base.context.model_copy(
        update={
            "references": base.context.references.model_copy(
                update={"approved_configuration": approved}
            )
        }
    )
    seed = next(item for item in base.signals if item.signal_id == rule.signal_id)
    signals = tuple(
        seed.model_copy(update={"target_id": f"target.boundary.{index:05d}"})
        for index in range(maximum_signals)
    )

    request = DetectIdentificationArtifactsRequest(
        context=context,
        detector_profile=profile,
        policy=policy,
        rules=(rule,),
        signals=signals,
    )

    assert len(request.signals) == maximum_signals
    assert maximum_signals == M0205_MAX_SIGNALS
    assert maximum_signals == M0205_MAX_FLAGS
    assert len(request.rules) <= M0205_MAX_RULES
