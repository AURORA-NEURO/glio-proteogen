"""Compact fail-closed relational boundary tests for M01-05."""

from __future__ import annotations

from typing import Final

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactDetectionPolicy,
    ArtifactDetectionResult,
    ArtifactFlag,
    ArtifactRule,
    Comparison,
    DetectArtifactsRequest,
    DetectionDisposition,
    DetectorProfile,
    ExclusionMask,
    FlagDisposition,
    FlagProvenance,
    PosteriorEstimate,
    PosteriorState,
    SignalObservation,
    SignalState,
    configuration_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    ExecutionContext,
    IdentityLineageState,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection import detect_artifacts
from tests.contract.test_m01_05_contract import _artifact, _digest, _request, _rule

pytestmark = pytest.mark.contract

_VALID_RESULT_DIGEST: Final = "sha256:" + ("1" * 64)
_FIRST_EXCESS_FLAG_TARGET_COUNT: Final = 5_001
_FIRST_EXCESS_PROVENANCE_SIGNAL_COUNT: Final = 9_992


@pytest.mark.parametrize(
    "update",
    [
        {"comparison": Comparison.BOOLEAN_EQUAL, "expected_bool": None, "threshold": None},
        {"comparison": Comparison.BOOLEAN_EQUAL, "expected_bool": True, "threshold": 0.5},
        {
            "comparison": Comparison.BOOLEAN_EQUAL,
            "expected_bool": True,
            "threshold": None,
            "unit": "fraction",
        },
        {"threshold": None},
        {"unit": None},
        {"comparison": Comparison.WITHIN_RANGE, "upper_threshold": None},
        {"comparison": Comparison.WITHIN_RANGE, "threshold": 0.8, "upper_threshold": 0.2},
        {"posterior_if_triggered": 0.1, "posterior_if_clear": 0.2},
    ],
)
def test_rule_shapes_fail_closed(update: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ArtifactRule(**{**_rule().model_dump(mode="python"), **update})


def test_duplicate_profile_policy_signal_and_provenance_values_reject() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="profile rule identifiers"):
        DetectorProfile(
            **{
                **request.detector_profile.model_dump(mode="python"),
                "required_rule_ids": (request.rules[0].rule_id,) * 2,
            }
        )
    with pytest.raises(ValidationError, match="enabled artifact classes"):
        ArtifactDetectionPolicy(
            **{
                **request.policy.model_dump(mode="python"),
                "enabled_classes": (ArtifactClass.TECHNICAL,) * 2,
            }
        )
    with pytest.raises(ValidationError, match="signal evidence"):
        SignalObservation(
            **{
                **request.signals[0].model_dump(mode="python"),
                "evidence": (request.signals[0].evidence[0],) * 2,
            }
        )
    with pytest.raises(ValidationError, match="flag rule digests"):
        FlagProvenance(
            configuration_digest=_digest("configuration"),
            rule_digests=(_digest("rule"),) * 2,
        )
    with pytest.raises(ValidationError, match="flag signal digests"):
        FlagProvenance(
            configuration_digest=_digest("configuration"),
            rule_digests=(_digest("rule"),),
            signal_digests=(_digest("signal"),) * 2,
        )


def test_signal_state_and_posterior_state_shapes_reject() -> None:
    with pytest.raises(ValidationError, match="observed artifact signal requires"):
        SignalObservation(
            target_id="target.one",
            signal_id="signal.one",
            state=SignalState.OBSERVED,
            evidence=(_artifact("signal"),),
        )
    with pytest.raises(ValidationError, match="estimated artifact posterior"):
        PosteriorEstimate(state=PosteriorState.ESTIMATED)
    with pytest.raises(ValidationError, match="non-evaluable artifact posterior"):
        PosteriorEstimate(state=PosteriorState.NOT_EVALUABLE, value=0.0)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_rule", "artifact rule identifiers"),
        ("duplicate_signal", "target/identifier pairs"),
        ("rule_cap", "exceeds the active policy"),
        ("signal_cap", "exceeds the active policy"),
        ("undefined_required", "undefined required rule"),
        ("disabled_class", "class is disabled"),
        ("unknown_signal", "unknown signal"),
    ],
)
def test_request_closure_rejects_relational_mismatch(mutation: str, message: str) -> None:
    request = _request()
    updates: dict[str, object] = {}
    if mutation == "duplicate_rule":
        updates["rules"] = request.rules * 2
    elif mutation == "duplicate_signal":
        updates["signals"] = request.signals * 2
    elif mutation == "rule_cap":
        updates["policy"] = request.policy.model_copy(update={"max_rules": 1})
        extra = request.rules[0].model_copy(update={"rule_id": "rule.extra"})
        updates["rules"] = (*request.rules, extra)
    elif mutation == "signal_cap":
        updates["policy"] = request.policy.model_copy(update={"max_signals": 1})
        extra = request.signals[0].model_copy(update={"target_id": "target.extra"})
        updates["signals"] = (*request.signals, extra)
    elif mutation == "undefined_required":
        updates["detector_profile"] = request.detector_profile.model_copy(
            update={"required_rule_ids": ("rule.undefined",)}
        )
    elif mutation == "disabled_class":
        updates["policy"] = request.policy.model_copy(
            update={"enabled_classes": (ArtifactClass.BATCH,)}
        )
    else:
        updates["rules"] = (
            request.rules[0].model_copy(update={"signal_id": "signal.unknown"}),
        )

    with pytest.raises(ValidationError, match=message):
        DetectArtifactsRequest(**{**request.model_dump(mode="python"), **updates})


def test_request_rejects_first_excess_derived_flag_count() -> None:
    request = _request()
    rules = (request.rules[0], _rule("batch"))
    profile = DetectorProfile(
        profile_id=request.detector_profile.profile_id,
        version=request.detector_profile.version,
        required_rule_ids=tuple(rule.rule_id for rule in rules),
        evidence=request.detector_profile.evidence,
    )
    signals = (
        *(
            request.signals[0].model_copy(update={"target_id": f"target.{index:05d}"})
            for index in range(_FIRST_EXCESS_FLAG_TARGET_COUNT)
        ),
        request.signals[0].model_copy(
            update={"target_id": "target.00000", "signal_id": rules[1].signal_id}
        ),
    )
    context = _request_context_for(request, profile, rules)

    with pytest.raises(ValidationError, match="result flag limit"):
        DetectArtifactsRequest(
            context=context,
            detector_profile=profile,
            policy=request.policy,
            rules=rules,
            signals=signals,
        )


def test_request_rejects_first_excess_provenance_input_count() -> None:
    request = _request()
    signals = tuple(
        request.signals[0].model_copy(update={"target_id": f"target.{index:05d}"})
        for index in range(_FIRST_EXCESS_PROVENANCE_SIGNAL_COUNT)
    )

    with pytest.raises(ValidationError, match="provenance input limit"):
        DetectArtifactsRequest(
            context=request.context,
            detector_profile=request.detector_profile,
            policy=request.policy,
            rules=request.rules,
            signals=signals,
        )


def _request_context_for(
    request: DetectArtifactsRequest,
    profile: DetectorProfile,
    rules: tuple[ArtifactRule, ...],
) -> ExecutionContext:
    configuration = configuration_digest(profile, request.policy, rules)
    approved = request.context.references.approved_configuration.model_copy(
        update={
            "evidence": request.context.references.approved_configuration.evidence.model_copy(
                update={"digest": configuration}
            )
        }
    )
    references = request.context.references.model_copy(
        update={"approved_configuration": approved}
    )
    return request.context.model_copy(update={"references": references})


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "every upstream control"),
    ],
)
def test_request_authorization_rejects_each_control_family(
    role: str,
    state: object,
    message: str,
) -> None:
    request = _request()
    reference = getattr(request.context.references, role).model_copy(update={"state": state})
    references = request.context.references.model_copy(update={role: reference})
    context = request.context.model_copy(update={"references": references})

    with pytest.raises(ValidationError, match=message):
        DetectArtifactsRequest(**{**request.model_dump(mode="python"), "context": context})


def test_flag_and_mask_relational_shapes_reject() -> None:
    base = ArtifactFlag(
        target_id="target.one",
        artifact_class=ArtifactClass.TECHNICAL,
        posterior=PosteriorEstimate(state=PosteriorState.ESTIMATED, value=0.1),
        disposition=FlagDisposition.CLEAR,
        rule_ids=("rule.one",),
        provenance=FlagProvenance(
            configuration_digest=_digest("configuration"),
            rule_digests=(_digest("rule"),),
        ),
        evidence=(_artifact("flag"),),
    )
    with pytest.raises(ValidationError, match="rule identifiers"):
        ArtifactFlag(
            **{**base.model_dump(mode="python"), "rule_ids": ("rule.one",) * 2}
        )
    with pytest.raises(ValidationError, match="evidence references"):
        ArtifactFlag(
            **{
                **base.model_dump(mode="python"),
                "evidence": (_artifact("flag"),) * 2,
            }
        )
    with pytest.raises(ValidationError, match="contradicts posterior"):
        ArtifactFlag(
            **{
                **base.model_dump(mode="python"),
                "disposition": FlagDisposition.NOT_EVALUABLE,
            }
        )
    with pytest.raises(ValidationError, match="target identifiers"):
        ExclusionMask(excluded_target_ids=("target.one",) * 2)
    with pytest.raises(ValidationError, match="must be disjoint"):
        ExclusionMask(
            excluded_target_ids=("target.one",),
            review_target_ids=("target.one",),
        )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"exclusion_mask": ExclusionMask()}, "mask contradicts"),
        ({"disposition": DetectionDisposition.ACCEPTED}, "disposition contradicts"),
        ({"human_review_required": False}, "review flag contradicts"),
        ({"detection_id": "detection.wrong"}, "identifier does not bind"),
        ({"result_digest": _VALID_RESULT_DIGEST}, "digest does not match"),
    ],
)
def test_result_envelope_rejects_tampering(update: dict[str, object], message: str) -> None:
    result = detect_artifacts(_request())

    with pytest.raises(ValidationError, match=message):
        ArtifactDetectionResult(**{**result.model_dump(mode="python"), **update})
