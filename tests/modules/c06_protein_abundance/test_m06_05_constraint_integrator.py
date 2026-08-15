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
    ConstraintEvaluationOutcome,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsRequest,
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
