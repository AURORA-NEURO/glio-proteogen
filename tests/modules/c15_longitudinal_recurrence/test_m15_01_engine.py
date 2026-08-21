"""M15-01 runtime, replay, authorization, and safety tests."""

# ruff: noqa: TRY003

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import pytest

from glio_proteogen.contracts.m15_01 import (
    M1501_OUTPUT_MEDIA_TYPE,
    BiologicalHypothesis,
    CompetingExplanation,
    EvidenceTier,
    FalsificationOutcome,
    FalsificationRule,
    HypothesisEvaluationStatus,
    HypothesisStatus,
    RegisterComplexActivityHypothesesRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_01_biological_hypothesis_registry import (  # noqa: E501
    M1501AuthorizationError,
    M1501HypothesisRegistry,
    M1501InferenceError,
    M1501ReplayVerificationError,
    preflight_hypothesis_authorization,
    register_complex_activity_hypotheses,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


class RequestKwargs(TypedDict, total=False):
    accepted: bool
    statement: str
    tier_label: str
    rule_failure: str
    status: HypothesisStatus


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1501": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M15-01 registry evidence.",
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _hypothesis(
    *,
    statement: str = "Complex activity is associated with the declared proteotype state.",
    tier_label: str = "locked",
    rule_failure: str = "The evidence remains compatible with the mechanism.",
    status: HypothesisStatus = HypothesisStatus.PROPOSED,
) -> BiologicalHypothesis:
    evidence = _evidence("hypothesis")
    return BiologicalHypothesis(
        hypothesis_id="hypothesis.complex",
        version="1.0.0",
        statement=statement,
        mechanism_class="sparse_nmf",
        target_ids=("complex.activity",),
        competing_explanations=(
            CompetingExplanation(
                explanation_id="explanation.alternate",
                statement="An alternate complex explains the signal.",
                distinction="Compare stoichiometric support.",
                required_evidence=(evidence,),
            ),
        ),
        falsification_rules=(
            FalsificationRule(
                rule_id="rule.support",
                criterion="Required evidence supports the mechanism.",
                failure_condition=rule_failure,
                required_evidence=(evidence,),
                prohibited_interpretation="No clinical advice.",
            ),
        ),
        evidence_tiers=(
            EvidenceTier(
                tier=1,
                label=tier_label,
                rationale="Reviewed evidence is available.",
                evidence=(evidence,),
            ),
        ),
        prohibited_interpretations=("Do not infer identity, consent, kinase state, or treatment.",),
        status=status,
        evidence=(evidence,),
    )


def _request(
    *,
    accepted: bool = True,
    statement: str = "Complex activity is associated with the declared proteotype state.",
    tier_label: str = "locked",
    rule_failure: str = "The evidence remains compatible with the mechanism.",
    status: HypothesisStatus = HypothesisStatus.PROPOSED,
) -> RegisterComplexActivityHypothesesRequest:
    return RegisterComplexActivityHypothesesRequest(
        request_id="request.m1501",
        context=ExecutionContext(
            request_id="request.m1501",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        registry_version="1.0.0",
        hypotheses=(
            _hypothesis(
                statement=statement,
                tier_label=tier_label,
                rule_failure=rule_failure,
                status=status,
            ),
        ),
        reviewer_id="reviewer.test",
        source_artifacts=(
            _artifact("proteome"),
            _artifact("genome"),
            _artifact("transcriptome"),
            _artifact("ptm"),
        ),
    )


def test_supported_registry_is_deterministic_and_replayable() -> None:
    engine = M1501HypothesisRegistry()
    result = engine.infer(_request())
    assert result.status is HypothesisStatus.SUPPORTED
    assert result.registry is not None
    assert result.parent_target == "complex_activity"
    assert result.emits_parent is False
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.uncertainty.measurement.probability is None
    assert result.falsification_evaluations[0].outcome is FalsificationOutcome.PASSED
    assert engine.verify(result) == result


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"tier_label": "unsupported"}, HypothesisEvaluationStatus.NOT_EVALUABLE),
        ({"rule_failure": "Evidence is absent."}, HypothesisEvaluationStatus.SUPPORTED),
        (
            {"statement": "Treatment response should be recommended."},
            HypothesisEvaluationStatus.ABSTAINED,
        ),
        ({"status": HypothesisStatus.CONFLICTED}, HypothesisEvaluationStatus.CONFLICTED),
    ],
)
def test_unsupported_failed_prohibited_and_conflicted_cases_abstain(
    kwargs: RequestKwargs, expected: HypothesisEvaluationStatus
) -> None:
    result = M1501HypothesisRegistry().infer(_request(**kwargs))
    assert result.status is HypothesisStatus.ABSTAINED
    assert result.registry is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert result.evaluations[0].status is expected


@pytest.mark.parametrize(
    "failure_condition",
    ["Evidence is unsupported.", "Abstain pending independent review."],
)
def test_not_evaluable_and_explicit_abstention_rules_are_safe(
    failure_condition: str,
) -> None:
    result = M1501HypothesisRegistry().infer(_request(rule_failure=failure_condition))
    assert result.status is HypothesisStatus.ABSTAINED
    assert result.falsification_evaluations[0].outcome is not FalsificationOutcome.PASSED


@pytest.mark.parametrize(
    "raw_request",
    [
        object(),
        {"context": None},
        {"context": {"references": None}},
        {"context": {"references": {"approved_configuration": None}}},
        {"context": {"references": {"approved_configuration": {"state": 1}}}},
    ],
)
def test_authorization_preflight_rejects_opaque_and_malformed_controls(
    raw_request: object,
) -> None:
    with pytest.raises(M1501AuthorizationError):
        preflight_hypothesis_authorization(raw_request)


def test_inference_and_replay_fail_closed_for_invalid_inputs() -> None:
    engine = M1501HypothesisRegistry()
    with pytest.raises(M1501InferenceError):
        engine.infer(_request().model_copy(update={"hypotheses": ()}))
    with pytest.raises(M1501ReplayVerificationError):
        engine.verify(object())
    assert (
        engine.verify(engine.infer(_request()), replay=False).status is HypothesisStatus.SUPPORTED
    )


def test_authorization_hostile_and_invalid_request_fail_closed() -> None:
    with pytest.raises(M1501AuthorizationError):
        M1501HypothesisRegistry().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse opaque content")

    with pytest.raises(M1501AuthorizationError):
        preflight_hypothesis_authorization(Hostile())
    malformed = _request().model_dump(mode="json")
    malformed.pop("hypotheses")
    with pytest.raises(M1501InferenceError):
        M1501HypothesisRegistry().infer(malformed)


def test_replay_tamper_canonical_and_public_operation() -> None:
    engine = M1501HypothesisRegistry()
    result = engine.infer(_request())
    assert canonical_json_bytes(result)
    with pytest.raises(M1501ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    assert engine.verify(result, replay=False) == result
    assert register_complex_activity_hypotheses(_request()).status is HypothesisStatus.SUPPORTED


def test_media_type_and_provisional_boundary_are_explicit() -> None:
    assert M1501_OUTPUT_MEDIA_TYPE.endswith("m15-01+json")
