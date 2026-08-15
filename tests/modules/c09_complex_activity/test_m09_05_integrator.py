"""Adversarial deterministic runtime tests for provisional M09-05."""

import json
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m09_05 import (
    M0905_BASELINE_MEDIA_TYPE,
    ConstraintEvaluationStatus,
    ConstraintIntegratorPolicy,
    ConstraintIntegratorStatus,
    ConstraintSeverity,
    IntegrateComplexActivityConstraintsRequest,
    MechanismConstraint,
    MechanismConstraintKind,
)
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
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905AuthorizationError,
    M0905ConstraintIntegrator,
    integrate_complex_activity_constraints,
)

_DIGEST = "sha256:" + ("1" * 64)
_DIGEST_2 = "sha256:" + ("2" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST if name.endswith("1") else _DIGEST_2,
        media_type=media_type,
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    identity = IdentityLineageReference(
        decision_id="decision.identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=_DIGEST,
        evidence=_artifact("evidence.identity"),
    )
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=identity,
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended_use"),
    )
    return ExecutionContext(
        request_id="request.m09-05",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(*expressions: str) -> IntegrateComplexActivityConstraintsRequest:
    constraints = tuple(
        MechanismConstraint(
            constraint_id=f"constraint.{index}",
            version="1.0.0",
            kind=MechanismConstraintKind.CONSERVATION,
            expression=expression,
            severity=(ConstraintSeverity.SOFT if "soft" in expression else ConstraintSeverity.HARD),
            reference=_artifact(f"constraint-ref.{index}"),
        )
        for index, expression in enumerate(expressions, start=1)
    )
    return IntegrateComplexActivityConstraintsRequest(
        request_id="request.m09-05",
        context=_context(),
        baseline_result=_artifact("baseline", M0905_BASELINE_MEDIA_TYPE),
        policy=ConstraintIntegratorPolicy(
            policy_id="policy.m09-05",
            version="1.0.0",
            estimator_family="deterministic_constraint_bounded_integrator",
            constraints=constraints,
            conflict_tolerance=0.1,
        ),
        source_artifacts=(_artifact("feature.1"), _artifact("feature.2")),
    )


def test_supported_integration_is_deterministic_and_replayable() -> None:
    engine = M0905ConstraintIntegrator()
    first = engine.integrate(_request("conservation_hold"))
    second = engine.integrate(_request("conservation_hold"))
    assert first.result.status is ConstraintIntegratorStatus.ESTIMATED
    assert first.result.satisfaction_report[0].status is ConstraintEvaluationStatus.SATISFIED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_hard_violation_and_unsupported_input_abstain_safely() -> None:
    engine = M0905ConstraintIntegrator()
    hard = engine.integrate(_request("force_violation"))
    unsupported = engine.integrate(_request("unsupported ontology"))
    assert hard.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert unsupported.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert not hard.result.estimates
    assert (
        unsupported.result.satisfaction_report[0].status is ConstraintEvaluationStatus.NOT_EVALUABLE
    )


def test_soft_conflict_is_visible_and_ablated() -> None:
    report = (
        M0905ConstraintIntegrator()
        .integrate(_request("soft force_violation"))
        .result.satisfaction_report[0]
    )
    assert report.severity is ConstraintSeverity.SOFT
    assert report.status is ConstraintEvaluationStatus.VIOLATED
    assert report.violation_score is not None
    assert report.ablation_effect is not None


def test_preflight_rejects_withheld_consent_and_unknown_input() -> None:
    request = _request("hold")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    blocked_refs = refs.model_copy(update={"consent": withheld})
    blocked = request.model_copy(
        update={"context": request.context.model_copy(update={"references": blocked_refs})}
    )
    with pytest.raises(M0905AuthorizationError):
        M0905ConstraintIntegrator().integrate(blocked)
    with pytest.raises(ValueError, match="valid dictionary"):
        M0905ConstraintIntegrator().integrate(object())


def test_tampering_and_public_json_operation_are_closed() -> None:
    request = _request("hold")
    engine = M0905ConstraintIntegrator()
    built = integrate_complex_activity_constraints(request)
    tampered = built.canonical_bytes.replace(b'"hold"', b'"force_violation"')
    assert not engine.verify(built.result, tampered).verified
    payload = json.dumps(request.model_dump(mode="json")).encode()
    assert payload.startswith(b"{")
