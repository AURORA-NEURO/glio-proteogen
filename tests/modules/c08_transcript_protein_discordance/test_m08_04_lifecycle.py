"""Lifecycle, replay, and architecture matrix tests for provisional M08-04."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import glio_proteogen.modules.c08_transcript_protein_discordance.m08_04_probabilistic_estimator.engine as engine_module  # noqa: E501
from glio_proteogen.contracts.m08_04 import (
    M0804_BASELINE_MEDIA_TYPE,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimatorConstraint,
    GliomaDiscordanceProgram,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticFeatureObservation,
    ProbabilisticFeatureState,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    TypedDiscordanceEvidenceState,
    TypedTranscriptProteinObservation,
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
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_04_probabilistic_estimator as m0804_runtime,
)

_EXPECTED_ESTIMATES = 2
_FIRST_CANDIDATE_CALL = 2
_TYPED_ESTIMATE_COUNT = 3
_POSTERIOR_MIDPOINT = 0.5
_ROBUST_CENTER_MAX = 0.5
_ARITHMETIC_MEAN_MIN = 1.0


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=sha256_digest({"artifact": name}),
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
    return ExecutionContext(
        request_id="request.m0804",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("evidence.identity"),
            ),
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended-use"),
        ),
    )


def _request(
    family: ProbabilisticEstimatorFamily = ProbabilisticEstimatorFamily.LEARNED,
    *,
    features: tuple[ProbabilisticFeatureObservation, ...] | None = None,
    source_name: str = "source.proteome",
) -> EstimateTranscriptProteinProbabilisticRequest:
    config = ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m0804",
        version="1.0.0",
        estimator_family=family,
        objective="locked.posterior.log-loss",
        priors=(
            ProbabilisticPrior(
                prior_id="prior.discordance",
                version="1.0.0",
                kind=ProbabilisticPriorKind.NORMAL,
                parameters=(0.25, 0.1),
            ),
        ),
        constraints=(
            EstimatorConstraint(
                constraint_id="constraint.isoform",
                expression="isoform_mass >= 0",
                hard=True,
            ),
        ),
        optimizer="deterministic.coordinate-descent",
        seed=17,
        max_iterations=100,
        reference=_artifact("reference.posterior"),
    )
    observed = features or (
        ProbabilisticFeatureObservation(
            feature_id="discordance.log-ratio",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            value=0.8,
            isoform_id="isoform.a",
            weight=1.0,
        ),
        ProbabilisticFeatureObservation(
            feature_id="discordance.ptm-shift",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            value=-0.2,
            isoform_id="isoform.b",
            weight=2.0,
        ),
    )
    return EstimateTranscriptProteinProbabilisticRequest(
        request_id="request.m0804",
        context=_context(),
        baseline_result=_artifact("baseline.m0803", M0804_BASELINE_MEDIA_TYPE),
        configuration=config,
        feature_observations=observed,
        source_artifacts=(_artifact(source_name), _artifact("source.transcriptome")),
    )


@pytest.mark.parametrize(
    "family",
    tuple(ProbabilisticEstimatorFamily),
)
def test_architecture_matrix_estimates_and_replays(
    family: ProbabilisticEstimatorFamily,
) -> None:
    service = m0804_runtime.M0804Service()
    request = _request(family)
    result = service.execute(request)
    assert result.status.value == "estimated"
    assert len(result.estimates) == _EXPECTED_ESTIMATES
    assert result.uncertainty.measurement.probability is not None
    assert service.replay(request, result) == result


def test_irls_posterior_tracks_signed_discordance_and_reliability() -> None:
    positive = (
        ProbabilisticFeatureObservation(
            feature_id="discordance.rna-high",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            value=2.0,
            isoform_id="isoform.a",
            weight=2.0,
        ),
        ProbabilisticFeatureObservation(
            feature_id="discordance.protein-high",
            state=ProbabilisticFeatureState.OBSERVED,
            unit="ratio",
            value=1.5,
            isoform_id="isoform.b",
            weight=1.0,
        ),
    )
    negative = tuple(
        item.model_copy(update={"value": -abs(item.value or 0.0)}) for item in positive
    )
    engine = m0804_runtime.M0804Service()
    positive_result = engine.execute(_request(features=positive))
    negative_result = engine.execute(_request(features=negative))

    positive_score = positive_result.estimates[0].estimate_value
    negative_score = negative_result.estimates[0].estimate_value
    assert positive_score is not None
    assert negative_score is not None
    assert positive_score > _POSTERIOR_MIDPOINT
    assert negative_score < positive_score
    assert positive_result.diagnostics[-1].iteration_count > 0
    assert positive_result.diagnostics[-1].convergence_gap is not None


def test_missing_and_out_of_domain_features_abstain() -> None:
    missing = ProbabilisticFeatureObservation(
        feature_id="discordance.missing",
        state=ProbabilisticFeatureState.MISSING,
        unit="ratio",
        weight=1.0,
    )
    result = m0804_runtime.M0804Service().execute(_request(features=(missing,)))
    assert result.status.value == "abstained"
    assert result.human_review_required is True
    assert result.estimates == ()

    ood = m0804_runtime.M0804Service().execute(_request(source_name="source.ood-domain"))
    assert ood.status.value == "abstained"
    assert "out_of_domain" in ood.finding_codes


def test_withheld_consent_fails_before_request_validation() -> None:
    request = _request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(m0804_runtime.M0804AuthorizationError):
        m0804_runtime.M0804Service().execute(request)


def test_plugin_typed_json_parity_and_tamper_rejection() -> None:
    service = m0804_runtime.M0804Service()
    plugin = m0804_runtime.M0804Plugin(service)
    request = _request()
    typed_token = plugin.validate(request)
    json_token = plugin.validate(request.model_dump_json())
    assert plugin.run(typed_token).model_dump(mode="json") == plugin.run(json_token).model_dump(
        mode="json"
    )
    result = service.execute(request)
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    with pytest.raises(ValueError, match="digest"):
        service.verify(tampered)


def test_typed_glioma_discordance_graph_bootstraps_and_replays() -> None:
    typed = (
        TypedTranscriptProteinObservation(
            observation_id="obs.egfr",
            feature_id="EGFR",
            gene="EGFR",
            program=GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR,
            state=TypedDiscordanceEvidenceState.OBSERVED,
            transcript_effect=0.4,
            protein_effect=1.1,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
        TypedTranscriptProteinObservation(
            observation_id="obs.cdk4",
            feature_id="CDK4",
            gene="CDK4",
            program=GliomaDiscordanceProgram.PROLIFERATION,
            state=TypedDiscordanceEvidenceState.OBSERVED,
            transcript_effect=0.6,
            protein_effect=1.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
        TypedTranscriptProteinObservation(
            observation_id="obs.tp53",
            feature_id="TP53",
            gene="TP53",
            program=GliomaDiscordanceProgram.P53_CELL_CYCLE,
            state=TypedDiscordanceEvidenceState.LEFT_CENSORED,
            transcript_effect=0.2,
            protein_censor_limit=0.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
    )
    request = _request().model_copy(
        update={"feature_observations": (), "typed_observations": typed}
    )
    service = m0804_runtime.M0804Service()
    result = service.execute(request)
    assert result.status.value == "estimated"
    assert result.typed_model is True
    assert result.model_family == "glioma-transcript-protein-discordance-program-irls/1.0.0"
    assert len(result.estimates) == _TYPED_ESTIMATE_COUNT
    assert result.diagnostics[0].objective_value is not None
    assert service.replay(request, result) == result
    reordered = request.model_copy(update={"typed_observations": tuple(reversed(typed))})
    assert service.execute(reordered) == result


def test_typed_solver_backtracks_an_objective_increasing_sweep(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    typed = (
        TypedTranscriptProteinObservation(
            observation_id="obs.egfr",
            feature_id="EGFR",
            gene="EGFR",
            program=GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR,
            state=TypedDiscordanceEvidenceState.OBSERVED,
            transcript_effect=0.4,
            protein_effect=1.1,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
        TypedTranscriptProteinObservation(
            observation_id="obs.cdk4",
            feature_id="CDK4",
            gene="CDK4",
            program=GliomaDiscordanceProgram.PROLIFERATION,
            state=TypedDiscordanceEvidenceState.OBSERVED,
            transcript_effect=0.6,
            protein_effect=1.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
        TypedTranscriptProteinObservation(
            observation_id="obs.tp53",
            feature_id="TP53",
            gene="TP53",
            program=GliomaDiscordanceProgram.P53_CELL_CYCLE,
            state=TypedDiscordanceEvidenceState.LEFT_CENSORED,
            transcript_effect=0.2,
            protein_censor_limit=0.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
    )
    original = engine_module._typed_objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == _FIRST_CANDIDATE_CALL else value

    monkeypatch.setattr(engine_module, "_typed_objective", objective)
    fit = engine_module._fit_typed(typed)
    assert fit is not None
    assert fit.converged is True
    assert calls > _FIRST_CANDIDATE_CALL
    assert all(
        after <= before + engine_module._TYPED_OBJECTIVE_TOLERANCE
        for before, after in zip(fit.trace[:-1], fit.trace[1:], strict=True)
    )


def test_typed_initialization_respects_left_censor_bounds() -> None:
    typed = (
        TypedTranscriptProteinObservation(
            observation_id="obs.observed",
            feature_id="EGFR",
            gene="EGFR",
            program=GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR,
            state=TypedDiscordanceEvidenceState.OBSERVED,
            transcript_effect=0.2,
            protein_effect=1.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
        TypedTranscriptProteinObservation(
            observation_id="obs.censored",
            feature_id="TP53",
            gene="TP53",
            program=GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR,
            state=TypedDiscordanceEvidenceState.LEFT_CENSORED,
            transcript_effect=0.1,
            protein_censor_limit=0.0,
            transcript_standard_error=0.15,
            protein_standard_error=0.2,
        ),
    )
    program_ids = (GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR.value,)
    values = engine_module._initial_typed_values(typed, program_ids)
    assert values == pytest.approx([-0.1])


def test_typed_initialization_downweights_failed_discordance_replicate() -> None:
    """Repeated transcript-protein effects use a robust Huber center."""

    terms = tuple((value, 0.2, False, 1.0) for value in (0.2, 0.25, 0.3, 4.0))
    center = engine_module._robust_initial_center(terms)
    arithmetic_mean = sum(term[0] for term in terms) / len(terms)
    assert center < _ROBUST_CENTER_MAX
    assert arithmetic_mean > _ARITHMETIC_MEAN_MIN
    assert engine_module._initial_measurement_objective(center, terms) <= (
        engine_module._initial_measurement_objective(arithmetic_mean, terms)
    )


def test_typed_glioma_discordance_requires_supported_program_coverage() -> None:
    observation = TypedTranscriptProteinObservation(
        observation_id="obs.egfr",
        feature_id="EGFR",
        gene="EGFR",
        program=GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR,
        state=TypedDiscordanceEvidenceState.OBSERVED,
        transcript_effect=0.4,
        protein_effect=1.1,
        transcript_standard_error=0.15,
        protein_standard_error=0.2,
    )
    request = _request().model_copy(
        update={"feature_observations": (), "typed_observations": (observation,)}
    )
    result = m0804_runtime.M0804Service().execute(request)
    assert result.status.value == "abstained"
    assert result.estimates == ()
    assert result.human_review_required is True
