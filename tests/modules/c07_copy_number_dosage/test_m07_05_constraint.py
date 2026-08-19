"""Lifecycle, replay, and safe-failure tests for M07-05."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m07_05 import (
    M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE,
    IntegrateProteotypeConstraintsRequest,
    ProteotypeConstraintAwareEstimate,
    ProteotypeConstraintEvaluationOutcome,
    ProteotypeConstraintHardness,
    ProteotypeConstraintKind,
    ProteotypeConstraintReplayReason,
    ProteotypeMechanismConstraint,
    ProteotypeMechanismConstraintSet,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    BuiltConstraintIntegration,
    ConstraintAuthorizationError,
    ConstraintInputError,
    M0705ConstraintEngine,
    integrate_proteotype_constraints,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    service as m0705_service,
)

_EXPECTED_ESTIMATES = 2


def _artifact(
    label: str,
    char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=label,
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0705.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{label}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0705.test",
        actor_id="actor.m0705.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0705.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("evidence.identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0705.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _request(*, force_hard_violation: bool = False) -> IntegrateProteotypeConstraintsRequest:
    hard = ProteotypeMechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="1.0.0",
        kind=ProteotypeConstraintKind.CHEMISTRY,
        hardness=ProteotypeConstraintHardness.HARD,
        expression="force_violation" if force_hard_violation else "abundance >= 0",
        feature_ids=("feature.proteotype",),
    )
    soft = ProteotypeMechanismConstraint(
        constraint_id="constraint.pathway",
        version="1.0.0",
        kind=ProteotypeConstraintKind.GRAPH,
        hardness=ProteotypeConstraintHardness.SOFT,
        expression="pathway coherence is favored",
        feature_ids=("feature.proteotype", "feature.residual"),
        weight=0.5,
    )
    return IntegrateProteotypeConstraintsRequest(
        request_id="request.m0705.test",
        context=_context(),
        representation_result=_artifact(
            "representation.m0702",
            "d",
            "application/vnd.glio-proteogen.m07-02+json",
        ),
        constraint_set=ProteotypeMechanismConstraintSet(
            constraint_set_id="constraint-set.reviewed",
            version="1.0.0",
            constraints=(hard, soft),
            reviewed_by="reviewer.m0705",
        ),
        advanced_estimator_result=_artifact(
            "estimator.m0704",
            "e",
            M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE,
        ),
        feature_artifacts=(
            _artifact("feature.proteotype", "1"),
            _artifact("feature.residual", "2"),
        ),
    )


def test_integrator_is_deterministic_and_emits_ablation_evidence() -> None:
    engine = M0705ConstraintEngine()
    first = engine.integrate(_request())
    second = engine.integrate(_request())
    assert first.result.status.value == "integrated"
    assert len(first.result.estimates) == _EXPECTED_ESTIMATES
    assert first.result.ablations[0].constraint_id == "constraint.pathway"
    assert first.canonical_bytes == second.canonical_bytes


def test_soft_conflict_remains_visible_without_hidden_prior_dominance() -> None:
    request = _request()
    soft = request.constraint_set.constraints[1].model_copy(
        update={"expression": "force_violation"}
    )
    constraint_set = request.constraint_set.model_copy(
        update={"constraints": (request.constraint_set.constraints[0], soft)}
    )
    built = M0705ConstraintEngine().integrate(
        request.model_copy(update={"constraint_set": constraint_set})
    )
    assert built.result.status.value == "integrated"
    assert built.result.evaluations[1].outcome is ProteotypeConstraintEvaluationOutcome.VIOLATED
    assert (
        built.result.ablations[0].effect_delta == built.result.ablations[0].with_constraint_effect
    )


def test_hard_violation_abstains_without_estimates() -> None:
    built = M0705ConstraintEngine().integrate(_request(force_hard_violation=True))
    assert built.result.status.value == "abstained"
    assert not built.result.estimates
    assert built.result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert "hard constraint" in (built.result.abstention_reason or "")


def test_missing_and_duplicate_features_abstain_safely() -> None:
    request = _request()
    missing_constraint = request.constraint_set.constraints[0].model_copy(
        update={"feature_ids": ("feature.missing",)}
    )
    missing_set = request.constraint_set.model_copy(
        update={"constraints": (missing_constraint, request.constraint_set.constraints[1])}
    )
    missing = M0705ConstraintEngine().integrate(
        request.model_copy(update={"constraint_set": missing_set})
    )
    duplicate = M0705ConstraintEngine().integrate(
        request.model_copy(update={"feature_artifacts": (request.feature_artifacts[0],) * 2})
    )
    assert missing.result.status.value == "abstained"
    assert duplicate.result.status.value == "abstained"
    assert not missing.result.estimates
    assert not duplicate.result.estimates
    assert (
        missing.result.evaluations[0].outcome is ProteotypeConstraintEvaluationOutcome.NOT_EVALUABLE
    )
    assert missing.result.evaluations[0].residual is None
    assert missing.result.evaluations[0].effect_size is None


def test_authorization_checks_consent_identity_and_controls() -> None:
    request = _request()
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(ConstraintAuthorizationError):
        M0705ConstraintEngine().integrate(denied)
    unresolved = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "identity_lineage": refs.identity_lineage.model_copy(
                                update={"state": IdentityLineageState.UNRESOLVED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(ConstraintAuthorizationError):
        M0705ConstraintEngine().integrate(unresolved)


def test_service_wrapper_and_strict_boundary() -> None:
    request = _request()
    service = m0705_service.M0705Service()
    built = service.execute(request)
    wrapper = integrate_proteotype_constraints(request)
    assert built.canonical_bytes == wrapper.canonical_bytes
    assert service.verify(built.result, built.canonical_bytes).verified
    with pytest.raises((TypeError, ValueError)):
        service.integrate(object())


def test_built_result_rejects_digest_and_noncanonical_bytes() -> None:
    built = M0705ConstraintEngine().integrate(_request())
    with pytest.raises(ConstraintInputError, match="digest"):
        BuiltConstraintIntegration(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
    with pytest.raises(ConstraintInputError, match="canonical"):
        BuiltConstraintIntegration(built.result, built.canonical_bytes + b" ")


def test_replay_invalid_and_non_bytes_fail_closed() -> None:
    engine = M0705ConstraintEngine()
    assert engine.verify(object()).reason is ProteotypeConstraintReplayReason.INVALID_RESULT
    built = engine.integrate(_request())
    replay = engine.verify(built.result, "not-bytes")  # type: ignore[arg-type]
    assert replay.verified is False
    assert replay.content_verified is False


def test_contract_shapes_and_canonical_digests_are_closed() -> None:
    request = _request()
    built = M0705ConstraintEngine().integrate(request)
    assert built.result.request_digest == canonical_request_digest(request)
    assert built.result.result_digest == result_payload_digest(built.result)
    with pytest.raises(ValueError, match="bounds"):
        ProteotypeConstraintAwareEstimate(
            feature_id="feature.bad",
            unit="unit",
            estimate_value=2.0,
            lower_bound=3.0,
            upper_bound=1.0,
        )
