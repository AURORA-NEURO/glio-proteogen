"""Lifecycle, replay, and architecture matrix tests for provisional M08-04."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_04 import (
    M0804_BASELINE_MEDIA_TYPE,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimatorConstraint,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticFeatureObservation,
    ProbabilisticFeatureState,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
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
    assert plugin.run(typed_token).model_dump(mode="json") == plugin.run(
        json_token
    ).model_dump(mode="json")
    result = service.execute(request)
    tampered = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    with pytest.raises(ValueError, match="digest"):
        service.verify(tampered)
