"""Lifecycle, replay, safety, and constraint semantics for M06-05."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_05 import (
    ConstraintAblationRecord,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsRequest,
    IntegrateProteinAbundanceConstraintsResult,
    MechanismConstraint,
    MechanismConstraintHardness,
    MechanismConstraintKind,
    MechanismConstraintSet,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    BuiltConstraintIntegration,
    ConstraintIntegrationAuthorizationError,
    ConstraintIntegrationInputError,
    M0605MechanismConstraintEngine,
    M0605Service,
    integrate_protein_abundance_constraints,
)

_SOFT_WEIGHT = 0.5
_OBSERVED_VALUE = 1.5


def _reference(
    label: str,
    digest_char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"evidence.m0605.{label}",
        version="1.0.0",
        digest=f"sha256:{digest_char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0605.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_reference(label),
    )


def _request(
    *,
    state: FormalStateMissingness = FormalStateMissingness.OBSERVED,
    expression: str = "protein.abundance >= 0",
) -> IntegrateProteinAbundanceConstraintsRequest:
    context = ExecutionContext(
        request_id="request.m0605.smoke",
        actor_id="actor.m0605.smoke",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0605.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=f"sha256:{'b' * 64}",
                evidence=_reference("identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0605.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_reference("consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )
    definition = FormalStateFeatureDefinition(
        feature_id="protein.abundance",
        version="1.0.0",
        value_kind=FormalStateFeatureValueKind.SCALAR,
        unit="normalized-abundance",
        allowed_missingness=(FormalStateMissingness.OBSERVED, FormalStateMissingness.MISSING,
                             FormalStateMissingness.UNSUPPORTED),
        domain_lower=0.0,
    )
    schema = FormalProteinStateSchema(
        schema_id="schema.formal-state",
        version="1.0.0",
        features=(definition,),
    )
    value = FormalStateFeatureValue(
        feature_id=definition.feature_id,
        state=state,
        unit=definition.unit,
        scalar_value=1.5 if state is FormalStateMissingness.OBSERVED else None,
    )
    hard = MechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="1.0.0",
        kind=MechanismConstraintKind.CHEMISTRY,
        hardness=MechanismConstraintHardness.HARD,
        expression=expression,
        feature_ids=(definition.feature_id,),
    )
    soft = MechanismConstraint(
        constraint_id="constraint.pathway",
        version="1.0.0",
        kind=MechanismConstraintKind.GRAPH,
        hardness=MechanismConstraintHardness.SOFT,
        expression="protein.abundance >= 1",
        feature_ids=(definition.feature_id,),
        weight=_SOFT_WEIGHT,
    )
    return IntegrateProteinAbundanceConstraintsRequest(
        request_id=context.request_id,
        context=context,
        state_schema=schema,
        feature_values=(value,),
        constraint_set=MechanismConstraintSet(
            constraint_set_id="constraint-set.reviewed",
            version="1.0.0",
            constraints=(hard, soft),
            reviewed_by="reviewer.constraints",
        ),
        advanced_estimator_result=_reference(
            "advanced", "d", "application/vnd.glio-proteogen.m06-04+json"
        ),
        source_artifacts=(_reference("proteome", "e"),),
    )


def test_integrator_is_deterministic_and_reports_constraint_satisfaction() -> None:
    first = M0605MechanismConstraintEngine().integrate(_request())
    second = M0605MechanismConstraintEngine().integrate(_request())

    assert first.result.status is ConstraintIntegrationStatus.INTEGRATED
    assert first.result.evaluations[0].outcome is ConstraintEvaluationOutcome.SATISFIED
    assert len(first.result.ablations) == 1
    assert first.result.ablations[0].effect_delta == _SOFT_WEIGHT
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.result_digest == second.result.result_digest
    assert first.result.emits_parent is False


def test_hard_violation_abstains_without_estimate() -> None:
    built = M0605MechanismConstraintEngine().integrate(
        _request(expression="protein.abundance >= 2")
    )
    assert built.result.status is ConstraintIntegrationStatus.ABSTAINED
    assert not built.result.estimates
    assert built.result.support_decision.status.value == "review_required"
    assert built.result.evaluations[0].outcome is ConstraintEvaluationOutcome.VIOLATED


@pytest.mark.parametrize(
    "state",
    [FormalStateMissingness.MISSING, FormalStateMissingness.UNSUPPORTED],
)
def test_missing_or_unsupported_features_fail_closed(state: FormalStateMissingness) -> None:
    built = M0605MechanismConstraintEngine().integrate(_request(state=state))
    assert built.result.status is ConstraintIntegrationStatus.ABSTAINED
    assert not built.result.estimates
    assert built.result.evaluations[0].outcome is ConstraintEvaluationOutcome.NOT_EVALUABLE


def test_unknown_expression_is_not_executed_and_abstains() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request(expression="__import__('os')"))
    assert built.result.status is ConstraintIntegrationStatus.ABSTAINED
    assert built.result.evaluations[0].outcome is ConstraintEvaluationOutcome.NOT_EVALUABLE


def test_replay_accepts_canonical_bytes_and_rejects_tamper() -> None:
    engine = M0605MechanismConstraintEngine()
    built = engine.integrate(_request())
    verified = engine.verify(built.result, built.canonical_bytes)
    tampered = built.canonical_bytes[:-1] + bytes([built.canonical_bytes[-1] ^ 1])
    rejected = engine.verify(built.result, tampered)
    assert verified.verified is True
    assert rejected.verified is False
    assert rejected.result_digest is None


def test_replay_rejects_invalid_object_and_non_bytes() -> None:
    engine = M0605MechanismConstraintEngine()
    built = engine.integrate(_request())
    assert engine.verify(object(), built.canonical_bytes).reason.value == "invalid_result"
    assert not engine.verify(built.result, bytearray(built.canonical_bytes)).verified  # type: ignore[arg-type]


def test_service_execute_and_wrapper_preserve_replay() -> None:
    request = _request()
    service_built = M0605Service().execute(request)
    wrapper_built = integrate_protein_abundance_constraints(request)
    assert service_built.canonical_bytes == wrapper_built.canonical_bytes
    assert M0605Service().verify(service_built.result, service_built.canonical_bytes).verified


def test_authorization_rejects_withheld_consent_and_unresolved_identity() -> None:
    request = _request()
    refs = request.context.references
    withheld = request.model_copy(
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
    for denied in (withheld, unresolved):
        with pytest.raises(ConstraintIntegrationAuthorizationError):
            M0605MechanismConstraintEngine().integrate(denied)


def test_mapping_request_cannot_bypass_authorization() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD

    with pytest.raises(ConstraintIntegrationAuthorizationError):
        M0605MechanismConstraintEngine().integrate(payload)


def test_result_digest_and_canonical_bytes_are_closed() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    assert built.result.result_digest == result_payload_digest(built.result)
    assert built.canonical_bytes == canonical_json_bytes(built.result.model_dump(mode="json"))
    with pytest.raises(ConstraintIntegrationInputError, match="not canonical"):
        BuiltConstraintIntegration(built.result, b"{}")


def test_strict_request_boundary_rejects_untyped_object() -> None:
    with pytest.raises((TypeError, ValueError)):
        M0605MechanismConstraintEngine().integrate(object())


def test_result_limit_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator.engine.M0605_MAX_CANONICAL_RESULT_BYTES",
        1,
    )
    with pytest.raises(ConstraintIntegrationInputError, match="byte limit"):
        M0605MechanismConstraintEngine().integrate(_request())


def _rebuild_result(
    built: BuiltConstraintIntegration,
    **updates: object,
) -> IntegrateProteinAbundanceConstraintsResult:
    candidate = built.result.model_copy(update=updates)
    candidate = candidate.model_copy(update={"result_digest": result_payload_digest(candidate)})
    return type(built.result).model_validate(candidate, strict=True)


def test_result_validator_rejects_stale_request_digest() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    with pytest.raises(ValueError, match="request digest"):
        _rebuild_result(built, request_digest="sha256:" + "0" * 64)


def test_result_validator_rejects_missing_or_duplicate_evaluations() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    with pytest.raises(ValueError, match="evaluations must be unique"):
        _rebuild_result(built, evaluations=(built.result.evaluations[0],) * 2)
    with pytest.raises(ValueError, match="evaluate every"):
        _rebuild_result(built, evaluations=(built.result.evaluations[0],))


def test_result_validator_rejects_invalid_ablation_sets() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    soft = built.result.ablations[0]
    hard = ConstraintAblationRecord(
        constraint_id="constraint.nonnegative",
        with_constraint_effect=0.0,
        without_constraint_effect=0.0,
        effect_delta=0.0,
    )
    with pytest.raises(ValueError, match="every soft"):
        _rebuild_result(built, ablations=())
    with pytest.raises(ValueError, match="ablations must be unique"):
        _rebuild_result(built, ablations=(soft, soft))
    with pytest.raises(ValueError, match="hard constraints"):
        _rebuild_result(built, ablations=(soft, hard))


def test_result_validator_rejects_invalid_estimates() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    estimate = built.result.estimates[0]
    unknown = estimate.model_copy(update={"feature_id": "feature.unknown"})
    with pytest.raises(ValueError, match="estimate feature ids"):
        _rebuild_result(built, estimates=(estimate, estimate))
    with pytest.raises(ValueError, match="unknown feature"):
        _rebuild_result(built, estimates=(unknown,))


def test_result_validator_rejects_status_support_and_digest_conflicts() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    limited = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="test.review",
        rationale="review is required",
    )
    violated = ConstraintEvaluation(
        constraint_id="constraint.nonnegative",
        outcome=ConstraintEvaluationOutcome.VIOLATED,
        residual=-1.0,
        effect_size=0.0,
        message="hard constraint violated",
    )
    with pytest.raises(ValueError, match="requires estimates"):
        _rebuild_result(built, estimates=())
    with pytest.raises(ValueError, match="no hard violation"):
        _rebuild_result(
            built,
            evaluations=(violated, built.result.evaluations[1]),
        )
    with pytest.raises(ValueError, match="supported status"):
        _rebuild_result(built, support_decision=limited)
    with pytest.raises(ValueError, match="no hard violation"):
        _rebuild_result(built, abstention_reason="unexpected")
    candidate = built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="digest"):
        type(built.result).model_validate(candidate, strict=True)


def test_abstained_result_requires_reason_no_estimate_and_safe_support() -> None:
    built = M0605MechanismConstraintEngine().integrate(_request())
    supported = SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="test.supported",
        rationale="support is present",
    )
    with pytest.raises(ValueError, match="no estimates"):
        _rebuild_result(
            built,
            status=ConstraintIntegrationStatus.ABSTAINED,
            abstention_reason="review",
            estimates=built.result.estimates,
            support_decision=SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="test.unsupported",
                rationale="unsupported",
            ),
        )
    with pytest.raises(ValueError, match="reason"):
        _rebuild_result(
            built,
            status=ConstraintIntegrationStatus.ABSTAINED,
            estimates=(),
            abstention_reason=None,
            support_decision=SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="test.unsupported",
                rationale="unsupported",
            ),
        )
    with pytest.raises(ValueError, match="safe status"):
        _rebuild_result(
            built,
            status=ConstraintIntegrationStatus.ABSTAINED,
            estimates=(),
            abstention_reason="review",
            support_decision=supported,
        )


def test_engine_covers_comparison_operators_intervals_and_categorical_no_estimate() -> None:
    engine = M0605MechanismConstraintEngine()
    for operator in ("<=", ">", "<", "=="):
        result = engine.integrate(_request(expression=f"protein.abundance {operator} 1.5"))
        assert result.result.evaluations[0].outcome in {
            ConstraintEvaluationOutcome.SATISFIED,
            ConstraintEvaluationOutcome.VIOLATED,
        }
    request = _request()
    interval = request.feature_values[0].model_copy(
        update={"scalar_value": None, "interval_lower": 1.0, "interval_upper": 2.0}
    )
    interval_result = engine.integrate(request.model_copy(update={"feature_values": (interval,)}))
    assert interval_result.result.estimates[0].estimate_value == _OBSERVED_VALUE
    categorical = request.feature_values[0].model_copy(
        update={"scalar_value": None, "category": "A"}
    )
    categorical_result = engine.integrate(
        request.model_copy(update={"feature_values": (categorical,)})
    )
    assert categorical_result.result.status is ConstraintIntegrationStatus.ABSTAINED


def test_engine_rejects_control_state_and_bad_built_digest() -> None:
    request = _request()
    refs = request.context.references
    rejected = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "support": refs.support.model_copy(
                                update={"state": UpstreamDecisionState.REJECTED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(ConstraintIntegrationAuthorizationError):
        M0605MechanismConstraintEngine().integrate(rejected)
    built = M0605MechanismConstraintEngine().integrate(request)
    with pytest.raises(ConstraintIntegrationInputError, match="digest"):
        BuiltConstraintIntegration(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
