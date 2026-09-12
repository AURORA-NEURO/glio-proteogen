"""Lifecycle, replay, and safe-failure tests for M07-05."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

import pytest

import glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator.engine as engine_module  # noqa: E501
from glio_proteogen.contracts.m07_05 import (
    M0705_ADVANCED_ESTIMATOR_MEDIA_TYPE,
    DosageEvidenceState,
    GliomaDosageObservation,
    GliomaDosageProgram,
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
_FIRST_CANDIDATE_CALL = 2
_ROBUST_CENTER_MAX = 0.5
_ARITHMETIC_MEAN_MIN = 1.0


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


def _typed_observations() -> tuple[GliomaDosageObservation, ...]:
    return (
        GliomaDosageObservation(
            observation_id="observation.egfr",
            feature_id="feature.proteotype",
            program=GliomaDosageProgram.RTK_PI3K_AKT_MTOR,
            evidence_state=DosageEvidenceState.OBSERVED,
            standardized_effect=1.1,
            standard_error=0.2,
        ),
        GliomaDosageObservation(
            observation_id="observation.tp53",
            feature_id="feature.residual",
            program=GliomaDosageProgram.P53_DNA_REPAIR,
            evidence_state=DosageEvidenceState.OBSERVED,
            standardized_effect=-0.6,
            standard_error=0.25,
        ),
        GliomaDosageObservation(
            observation_id="observation.ccnd1",
            feature_id="feature.egfr",
            program=GliomaDosageProgram.CELL_CYCLE,
            evidence_state=DosageEvidenceState.LEFT_CENSORED,
            censoring_limit=0.1,
            standard_error=0.2,
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


def test_typed_glioma_dosage_fit_is_replayable_and_constrained() -> None:
    request = _request().model_copy(update={"typed_observations": _typed_observations()})
    reordered = _request().model_copy(
        update={"typed_observations": tuple(reversed(_typed_observations()))}
    )
    engine = M0705ConstraintEngine()
    first = engine.integrate(request)
    second = engine.integrate(request)
    reordered_result = engine.integrate(reordered)
    assert first.result.status.value == "integrated"
    assert first.result.model_family == "glioma-dosage-mechanism-irls/1.0.0"
    assert len(first.result.estimates) == len(_typed_observations())
    assert all(item.model_family == first.result.model_family for item in first.result.estimates)
    assert first.result.optimization_diagnostics[0].objective_trace_digest is not None
    assert first.result.optimization_diagnostics[0].status.value == "converged"
    assert first.canonical_bytes == second.canonical_bytes
    assert first.canonical_bytes == reordered_result.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_typed_dosage_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    original = engine_module._typed_objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == _FIRST_CANDIDATE_CALL else value

    monkeypatch.setattr(engine_module, "_typed_objective", objective)
    fitted = engine_module._fit_typed_dosage(_typed_observations(), max_iterations=64)
    assert fitted is not None
    assert calls > _FIRST_CANDIDATE_CALL
    trace = fitted[4]
    assert all(
        after <= before + engine_module._TYPED_OBJECTIVE_TOLERANCE
        for before, after in pairwise(trace)
    )


def test_typed_glioma_dosage_excludes_missing_and_abstains_without_program_support() -> None:
    missing = GliomaDosageObservation(
        observation_id="observation.missing",
        feature_id="feature.missing",
        evidence_state=DosageEvidenceState.MISSING,
        quality_weight=0.0,
    )
    request = _request().model_copy(
        update={"typed_observations": (*_typed_observations(), missing)}
    )
    result = M0705ConstraintEngine().integrate(request).result
    assert result.status.value == "integrated"
    assert all(item.evidence_count == 1 for item in result.estimates)
    unsupported_only = _request().model_copy(
        update={
            "typed_observations": (
                GliomaDosageObservation(
                    observation_id="observation.unsupported",
                    feature_id="feature.unsupported",
                    evidence_state=DosageEvidenceState.UNSUPPORTED,
                    quality_weight=0.0,
                ),
            )
        }
    )
    abstained = M0705ConstraintEngine().integrate(unsupported_only).result
    assert abstained.status.value == "abstained"
    assert not abstained.estimates


def test_typed_initialization_uses_observed_dosage_and_projects_censor_bounds() -> None:
    observed = _typed_observations()[0]
    censored = _typed_observations()[2].model_copy(
        update={
            "program": GliomaDosageProgram.RTK_PI3K_AKT_MTOR,
            "censoring_limit": -0.2,
        }
    )

    assert engine_module._initial_typed_program_state((observed, censored)) == pytest.approx(-0.2)


def test_typed_initialization_downweights_failed_dosage_replicate() -> None:
    terms = (
        (0.2, 0.2, 1.0),
        (0.3, 0.2, 1.0),
        (4.0, 0.2, 1.0),
    )

    center = engine_module._robust_initial_dosage_center(terms)
    arithmetic_mean = sum(term[0] for term in terms) / len(terms)

    assert center < _ROBUST_CENTER_MAX
    assert arithmetic_mean > _ARITHMETIC_MEAN_MIN
    assert engine_module._initial_dosage_measurement_objective(
        center, terms
    ) <= engine_module._initial_dosage_measurement_objective(arithmetic_mean, terms)


def test_typed_censor_only_initialization_is_neutral_when_limit_is_positive() -> None:
    censored = _typed_observations()[2]

    assert engine_module._initial_typed_program_state((censored,)) == pytest.approx(0.0)


def test_typed_offset_update_skips_feasible_censored_bounds() -> None:
    censored = _typed_observations()[2]
    program_indices = {
        program: index for index, program in enumerate(engine_module._TYPED_PROGRAMS)
    }
    programs = engine_module.np.zeros(len(engine_module._TYPED_PROGRAMS), dtype=float)
    offsets = engine_module.np.zeros(1, dtype=float)

    numerator, denominator = engine_module._typed_offset_terms(
        (censored,),
        feature_index=0,
        updated_programs=programs,
        offsets=offsets,
        program_indices=program_indices,
    )

    assert numerator == pytest.approx(0.0)
    assert denominator == pytest.approx(0.08)

    violating = censored.model_copy(update={"censoring_limit": -0.1})
    violating_numerator, violating_denominator = engine_module._typed_offset_terms(
        (violating,),
        feature_index=0,
        updated_programs=programs,
        offsets=offsets,
        program_indices=program_indices,
    )
    assert violating_numerator < 0.0
    assert violating_denominator > denominator


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
