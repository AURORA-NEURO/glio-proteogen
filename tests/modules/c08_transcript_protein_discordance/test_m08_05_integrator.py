"""Adversarial and deterministic runtime tests for provisional M08-05."""

from datetime import datetime, timezone

import pytest

from glio_proteogen.contracts.m08_05 import (
    M0805_BASELINE_MEDIA_TYPE,
    ConstraintEvaluationStatus,
    ConstraintIntegratorStatus,
    ConstraintIntegratorPolicy,
    ConstraintSeverity,
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
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805AuthorizationError,
    M0805ConstraintIntegrator,
    M0805Plugin,
    M0805Service,
    ValidatedM0805Request,
)
from glio_proteogen.contracts.m08_05 import (
    IntegrateTranscriptProteinConstraintsRequest,
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
        request_id="request.m08-05",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        references=refs,
    )


def _request(*expressions: str) -> IntegrateTranscriptProteinConstraintsRequest:
    references = (_artifact("feature.1"), _artifact("feature.2"))
    constraints = tuple(
        MechanismConstraint(
            constraint_id=f"constraint.{index}",
            version="1.0.0",
            kind=MechanismConstraintKind.CONSERVATION,
            expression=expression,
            severity=(
                ConstraintSeverity.SOFT
                if "soft" in expression
                else ConstraintSeverity.HARD
            ),
            reference=_artifact(f"constraint-ref.{index}"),
        )
        for index, expression in enumerate(expressions, start=1)
    )
    return IntegrateTranscriptProteinConstraintsRequest(
        request_id="request.m08-05",
        context=_context(),
        baseline_result=_artifact("baseline", M0805_BASELINE_MEDIA_TYPE),
        policy=ConstraintIntegratorPolicy(
            policy_id="policy.m08-05",
            version="1.0.0",
            estimator_family="deterministic_constraint_bounded_integrator",
            constraints=constraints,
            conflict_tolerance=0.1,
        ),
        source_artifacts=references,
    )


def test_supported_integration_is_deterministic_and_replayable() -> None:
    engine = M0805ConstraintIntegrator()
    first = engine.integrate(_request("conservation_hold"))
    second = engine.integrate(_request("conservation_hold"))

    assert first.result.status is ConstraintIntegratorStatus.ESTIMATED
    assert first.result.satisfaction_report[0].status is ConstraintEvaluationStatus.SATISFIED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_hard_violation_abstains_without_estimates() -> None:
    built = M0805Service().integrate(_request("force_violation"))

    assert built.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert not built.result.estimates
    assert built.result.support_decision.status.value == "review_required"
    assert built.result.abstention_reason is not None


def test_soft_conflict_is_visible_without_hidden_prior_dominance() -> None:
    built = M0805ConstraintIntegrator().integrate(_request("soft force_violation"))

    assert built.result.status is ConstraintIntegratorStatus.ESTIMATED
    report = built.result.satisfaction_report[0]
    assert report.severity is ConstraintSeverity.SOFT
    assert report.status is ConstraintEvaluationStatus.VIOLATED
    assert report.violation_score is not None


def test_unevaluable_constraint_abstains_safely() -> None:
    built = M0805ConstraintIntegrator().integrate(_request("unsupported ontology"))

    assert built.result.status is ConstraintIntegratorStatus.ABSTAINED
    assert built.result.satisfaction_report[0].status is ConstraintEvaluationStatus.NOT_EVALUABLE
    assert not built.result.estimates


def test_preflight_rejects_withheld_consent() -> None:
    request = _request("conservation_hold")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    request = request.model_copy(
        update={"context": request.context.model_copy(update={"references": refs.model_copy(update={"consent": withheld})})}
    )
    with pytest.raises(M0805AuthorizationError):
        M0805ConstraintIntegrator().integrate(request)


def test_replay_rejects_tampered_bytes_and_invalid_token() -> None:
    service = M0805Service()
    plugin = M0805Plugin(service)
    request = _request("conservation_hold")
    built = service.integrate(request)
    tampered = built.canonical_bytes.replace(b"conservation_hold", b"force_violation")
    verification = service.verify(built.result, tampered)

    assert not verification.verified
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0805Request(request=request, _seal=object()))
