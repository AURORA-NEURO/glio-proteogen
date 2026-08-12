"""Focused public-engine qualification for M01-05."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactDetectionPolicy,
    ArtifactRule,
    Comparison,
    DetectArtifactsRequest,
    DetectionDisposition,
    DetectorProfile,
    FlagDisposition,
    PosteriorState,
    SignalObservation,
    SignalState,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection import (
    M0105DetectionEngine,
    detect_artifacts,
)

_EXPECTED_FLAG_COUNT: Final = 4
_CLEAR_POSTERIOR: Final = 0.01
_REVIEW_POSTERIOR: Final = 0.8
_VERY_HIGH_POSTERIOR: Final = 0.99


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"fixture": label}),
        media_type="application/json",
    )


def _policy() -> ArtifactDetectionPolicy:
    return ArtifactDetectionPolicy(
        policy_id="policy.artifact",
        version="1.0.0",
        review_threshold=0.5,
        exclusion_threshold=0.9,
        enabled_classes=tuple(ArtifactClass),
    )


def _context(
    profile: DetectorProfile,
    policy: ArtifactDetectionPolicy,
    rules: tuple[ArtifactRule, ...],
) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.artifact",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision(
                "configuration",
                configuration_digest(profile, policy, rules),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"fixture": "identity"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _rule(
    identifier: str,
    artifact_class: ArtifactClass,
    signal_id: str,
    *,
    posterior: float = 0.95,
    exclusion_eligible: bool = True,
) -> ArtifactRule:
    return ArtifactRule(
        rule_id=identifier,
        version="1.0.0",
        artifact_class=artifact_class,
        signal_id=signal_id,
        comparison=Comparison.GREATER_THAN_OR_EQUAL,
        threshold=0.8,
        unit="ratio",
        posterior_if_triggered=posterior,
        posterior_if_clear=0.01,
        exclusion_eligible=exclusion_eligible,
    )


def _signal(
    target_id: str,
    signal_id: str,
    value: object,
    *,
    state: SignalState = SignalState.OBSERVED,
    unit: str | None = "ratio",
) -> SignalObservation:
    typed_value = value if isinstance(value, float | bool) else None
    return SignalObservation(
        target_id=target_id,
        signal_id=signal_id,
        state=state,
        value=typed_value,
        unit=unit,
        evidence=(_artifact(f"{target_id}-{signal_id}"),),
    )


def _request(
    rules: tuple[ArtifactRule, ...],
    signals: tuple[SignalObservation, ...],
) -> DetectArtifactsRequest:
    policy = _policy()
    profile = DetectorProfile(
        profile_id="detector.synthetic",
        version="1.0.0",
        required_rule_ids=tuple(rule.rule_id for rule in rules),
        evidence=_artifact("detector-profile"),
    )
    return DetectArtifactsRequest(
        context=_context(profile, policy, rules),
        detector_profile=profile,
        policy=policy,
        rules=rules,
        signals=signals,
    )


def test_engine_emits_one_flag_per_target_and_configured_class() -> None:
    rules = (
        _rule("rule.contamination", ArtifactClass.CONTAMINATION, "signal.contamination"),
        _rule("rule.batch", ArtifactClass.BATCH, "signal.batch"),
    )
    signals = (
        _signal("target.b", "signal.batch", 0.1),
        _signal("target.a", "signal.contamination", 0.95),
        _signal("target.a", "signal.batch", 0.1),
        _signal("target.b", "signal.contamination", 0.1),
    )
    request = _request(rules, signals)

    result = M0105DetectionEngine().detect(request)
    replay = detect_artifacts(request)

    assert replay == result
    assert len(result.flags) == _EXPECTED_FLAG_COUNT
    assert result.exclusion_mask.excluded_target_ids == ("target.a",)
    assert result.disposition is DetectionDisposition.QUARANTINED
    assert result.result_digest != "sha256:" + ("0" * 64)


def test_clear_result_uses_configured_posterior() -> None:
    rule = _rule("rule.clear", ArtifactClass.TECHNICAL, "signal.clear")
    result = detect_artifacts(_request((rule,), (_signal("target.a", "signal.clear", 0.1),)))

    flag = result.flags[0]
    assert flag.posterior.value == _CLEAR_POSTERIOR
    assert flag.disposition is FlagDisposition.CLEAR
    assert result.disposition is DetectionDisposition.ACCEPTED


@pytest.mark.parametrize("state", [SignalState.MISSING, SignalState.NOT_APPLICABLE])
def test_missing_required_signal_quarantines_for_review(state: SignalState) -> None:
    rule = _rule("rule.missing", ArtifactClass.MAPPING, "signal.missing")
    result = detect_artifacts(
        _request(
            (rule,),
            (_signal("target.a", "signal.missing", None, state=state),),
        )
    )

    flag = result.flags[0]
    assert flag.posterior.state is PosteriorState.NOT_EVALUABLE
    assert flag.posterior.value is None
    assert flag.disposition is FlagDisposition.NOT_EVALUABLE
    assert result.exclusion_mask.review_target_ids == ("target.a",)


def test_max_posterior_aggregation_does_not_assume_independence() -> None:
    rules = (
        _rule("rule.low", ArtifactClass.BATCH, "signal.low", posterior=0.6),
        _rule(
            "rule.high",
            ArtifactClass.BATCH,
            "signal.high",
            posterior=_REVIEW_POSTERIOR,
        ),
    )
    signals = (
        _signal("target.a", "signal.low", 0.9),
        _signal("target.a", "signal.high", 0.9),
    )
    result = detect_artifacts(_request(rules, signals))

    assert result.flags[0].posterior.value == _REVIEW_POSTERIOR
    assert result.flags[0].disposition is FlagDisposition.REVIEW


def test_exclusion_requires_at_least_one_eligible_rule() -> None:
    rule = _rule(
        "rule.review-only",
        ArtifactClass.LOW_COMPLEXITY,
        "signal.low-complexity",
        posterior=0.99,
        exclusion_eligible=False,
    )
    result = detect_artifacts(
        _request(
            (rule,),
            (_signal("target.a", "signal.low-complexity", 0.99),),
        )
    )

    assert result.flags[0].disposition is FlagDisposition.REVIEW
    assert result.exclusion_mask.excluded_target_ids == ()


@pytest.mark.parametrize(
    "signal",
    [
        _signal("target.a", "signal.numeric", value=True, unit=None),
        _signal("target.a", "signal.numeric", 0.9, unit="wrong"),
    ],
)
def test_type_or_unit_mismatch_is_rejected_at_request_boundary(
    signal: SignalObservation,
) -> None:
    rule = _rule("rule.numeric", ArtifactClass.TECHNICAL, "signal.numeric")

    with pytest.raises(ValueError, match="artifact signal"):
        _request((rule,), (signal,))


def test_boolean_rule_is_unitless_and_typed() -> None:
    rule = ArtifactRule(
        rule_id="rule.boolean",
        version="1.0.0",
        artifact_class=ArtifactClass.CONTEXT_FALSE_POSITIVE,
        signal_id="signal.context",
        comparison=Comparison.BOOLEAN_EQUAL,
        expected_bool=True,
        posterior_if_triggered=0.95,
        posterior_if_clear=0.01,
    )
    signal = _signal("target.a", "signal.context", value=True, unit=None)
    result = detect_artifacts(_request((rule,), (signal,)))

    assert result.flags[0].disposition is FlagDisposition.EXCLUDE
    references = {item.reference for item in result.evidence}
    assert result.request_digest in result.provenance.input_digests
    assert _request((rule,), (signal,)).detector_profile.evidence in references


def test_missing_all_signals_for_one_target_class_is_valid_not_evaluable() -> None:
    rules = (
        _rule("rule.technical", ArtifactClass.TECHNICAL, "signal.technical"),
        _rule("rule.batch", ArtifactClass.BATCH, "signal.batch"),
    )
    signals = (
        _signal("target.a", "signal.technical", 0.1),
        _signal("target.b", "signal.technical", 0.1),
        _signal("target.b", "signal.batch", 0.1),
    )

    result = detect_artifacts(_request(rules, signals))
    flags = {(item.target_id, item.artifact_class): item for item in result.flags}
    missing = flags[("target.a", ArtifactClass.BATCH)]

    assert missing.disposition is FlagDisposition.NOT_EVALUABLE
    assert missing.posterior.value is None
    assert missing.provenance.signal_digests == ()
    assert missing.evidence
    assert result.exclusion_mask.review_target_ids == ("target.a",)


def test_untriggered_eligible_rule_cannot_promote_ineligible_maximum() -> None:
    rules = (
        _rule(
            "rule.eligible-clear",
            ArtifactClass.CONTAMINATION,
            "signal.clear",
            posterior=0.95,
        ),
        _rule(
            "rule.ineligible-triggered",
            ArtifactClass.CONTAMINATION,
            "signal.triggered",
            posterior=_VERY_HIGH_POSTERIOR,
            exclusion_eligible=False,
        ),
    )
    signals = (
        _signal("target.a", "signal.clear", 0.1),
        _signal("target.a", "signal.triggered", 0.99),
    )

    result = detect_artifacts(_request(rules, signals))

    assert result.flags[0].posterior.value == _VERY_HIGH_POSTERIOR
    assert result.flags[0].disposition is FlagDisposition.REVIEW
