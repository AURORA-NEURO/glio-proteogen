"""Focused public-contract checks for M01-05 artifact detection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    ArtifactDetectionPolicy,
    ArtifactFlag,
    ArtifactRule,
    Comparison,
    DetectArtifactsRequest,
    DetectorProfile,
    FlagDisposition,
    FlagProvenance,
    PosteriorEstimate,
    PosteriorState,
    SignalObservation,
    SignalState,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
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

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_05.schema import ContractName

pytestmark = pytest.mark.contract


def _digest(label: str) -> str:
    return sha256_digest({"m0105": label})


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or _digest(label),
        media_type="application/json",
    )


def _rule(label: str = "technical") -> ArtifactRule:
    return ArtifactRule(
        rule_id=f"rule.{label}",
        version="1.0.0",
        artifact_class=ArtifactClass(label),
        signal_id=f"signal.{label}",
        comparison=Comparison.GREATER_THAN_OR_EQUAL,
        threshold=0.8,
        unit="fraction",
        posterior_if_triggered=0.95,
        posterior_if_clear=0.05,
    )


def _policy() -> ArtifactDetectionPolicy:
    return ArtifactDetectionPolicy(
        policy_id="policy.artifact",
        version="1.0.0",
        review_threshold=0.5,
        exclusion_threshold=0.9,
        enabled_classes=tuple(ArtifactClass),
    )


def _profile(rule: ArtifactRule) -> DetectorProfile:
    return DetectorProfile(
        profile_id="profile.artifact",
        version="1.0.0",
        required_rule_ids=(rule.rule_id,),
        evidence=_artifact("profile"),
    )


def _context(configuration: str) -> ExecutionContext:
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
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity-lineage"),
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


def _request() -> DetectArtifactsRequest:
    rule = _rule()
    policy = _policy()
    profile = _profile(rule)
    signal = SignalObservation(
        target_id="target.one",
        signal_id=rule.signal_id,
        state=SignalState.OBSERVED,
        value=0.9,
        unit="fraction",
        evidence=(_artifact("signal"),),
    )
    return DetectArtifactsRequest(
        context=_context(configuration_digest(profile, policy, (rule,))),
        detector_profile=profile,
        policy=policy,
        rules=(rule,),
        signals=(signal,),
    )


@pytest.mark.parametrize(
    "name",
    ["request", "output", "policy", "profile", "rule", "signal", "flag"],
)
def test_public_schema_is_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f":{name}")
    Draft202012Validator.check_schema(schema)


def test_contract_exposes_exact_seven_artifact_classes() -> None:
    assert {item.value for item in ArtifactClass} == {
        "technical",
        "contamination",
        "barcode_index",
        "batch",
        "low_complexity",
        "mapping",
        "context_false_positive",
    }


def test_request_digest_is_order_independent_for_enabled_classes() -> None:
    request = _request()
    policy = request.policy.model_copy(
        update={"enabled_classes": tuple(reversed(request.policy.enabled_classes))}
    )
    reordered = request.model_copy(update={"policy": policy})

    assert canonical_request_digest(reordered) == canonical_request_digest(request)


def test_non_observed_signal_never_carries_numeric_zero() -> None:
    with pytest.raises(ValidationError, match="cannot carry a value"):
        SignalObservation(
            target_id="target.one",
            signal_id="signal.missing",
            state=SignalState.MISSING,
            value=0.0,
            evidence=(_artifact("missing"),),
        )


def test_request_configuration_binds_profile_policy_and_rules() -> None:
    request = _request()
    changed_rule = request.rules[0].model_copy(update={"threshold": 0.7})

    with pytest.raises(ValidationError, match="does not bind the artifact detector"):
        DetectArtifactsRequest(
            context=request.context,
            detector_profile=request.detector_profile,
            policy=request.policy,
            rules=(changed_rule,),
            signals=request.signals,
        )


def test_policy_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="review threshold must be below"):
        ArtifactDetectionPolicy(
            policy_id="policy.invalid",
            version="1.0.0",
            review_threshold=0.9,
            exclusion_threshold=0.5,
            enabled_classes=(ArtifactClass.TECHNICAL,),
        )


def test_request_rejects_signal_unit_mismatch() -> None:
    request = _request()
    signal = request.signals[0].model_copy(update={"unit": "%"})

    with pytest.raises(ValidationError, match="unit must match"):
        DetectArtifactsRequest(
            context=request.context,
            detector_profile=request.detector_profile,
            policy=request.policy,
            rules=request.rules,
            signals=(signal,),
        )


def test_not_evaluable_flag_can_bind_rule_without_observed_signal() -> None:
    rule = _rule()
    profile_evidence = _artifact("profile")

    flag = ArtifactFlag(
        target_id="target.missing",
        artifact_class=rule.artifact_class,
        posterior=PosteriorEstimate(state=PosteriorState.NOT_EVALUABLE),
        disposition=FlagDisposition.NOT_EVALUABLE,
        rule_ids=(rule.rule_id,),
        provenance=FlagProvenance(
            configuration_digest=_digest("configuration"),
            rule_digests=(_digest("rule"),),
            signal_digests=(),
        ),
        evidence=(profile_evidence,),
    )

    assert flag.provenance.signal_digests == ()
    assert flag.evidence == (profile_evidence,)
