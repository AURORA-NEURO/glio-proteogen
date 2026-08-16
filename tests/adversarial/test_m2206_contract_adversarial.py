"""Adversarial contract and replay-identity closure for M22-06."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from glio_proteogen.contracts.m22_06 import (
    M2206_DOSSIER_SHA256,
    M2206_DOSSIER_SLICE,
    M2206_M2205_INPUT_MEDIA_TYPE,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ChallengeScenario,
    ChallengeSeverity,
    OODBand,
    RobustnessConfiguration,
    RobustnessObservation,
    RobustnessSurface,
    contract_json_schemas,
    result_identifier,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 8


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2206.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2206:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name), role="evidence", claim="M22-06 caller evidence."
    )


def _context(request_id: str = "request.m2206.synthetic") -> ExecutionContext:
    evidence = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2206.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2206.synthetic",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2206.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2206.identity"),
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2206.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> RobustnessConfiguration:
    return RobustnessConfiguration(
        configuration_id="configuration.m2206.synthetic",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.8,
        evidence=(_evidence("configuration"),),
    )


def _scenario(kind: ChallengeKind, index: int) -> ChallengeScenario:
    return ChallengeScenario(
        scenario_id=f"scenario.m2206.{index}",
        kind=kind,
        severity=ChallengeSeverity.ROUTINE,
        perturbation=f"locked {kind.value} perturbation",
        expected_disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        source_artifacts=(_artifact(f"scenario-{index}"),),
        evidence=(_evidence(f"scenario-evidence-{index}"),),
    )


def _observation(scenario: ChallengeScenario, index: int) -> RobustnessObservation:
    return RobustnessObservation(
        observation_id=f"observation.m2206.{index}",
        scenario_id=scenario.scenario_id,
        metric="robustness_delta",
        baseline_value=1.0,
        challenged_value=0.95,
        envelope_lower=0.8,
        envelope_upper=1.2,
        within_envelope=True,
        ood_score=0.1,
        ood_band=OODBand.IN_DOMAIN,
        disposition=ChallengeDisposition.WITHIN_ENVELOPE,
        evidence=(_evidence(f"observation-evidence-{index}"),),
    )


def _surface() -> RobustnessSurface:
    scenarios = tuple(_scenario(kind, index) for index, kind in enumerate(ChallengeKind))
    return RobustnessSurface(
        surface_id="surface.m2206.synthetic",
        version="1.0.0",
        scenarios=scenarios,
        observations=tuple(_observation(item, index) for index, item in enumerate(scenarios)),
        configuration=_configuration(),
        evidence=(_evidence("surface"),),
    )


def _request() -> ChallengeProteinRnaDiscordanceRobustnessRequest:
    upstream = _artifact("upstream", M2206_M2205_INPUT_MEDIA_TYPE)
    scenarios = tuple(_scenario(kind, index) for index, kind in enumerate(ChallengeKind))
    return ChallengeProteinRnaDiscordanceRobustnessRequest(
        request_id="request.m2206.synthetic",
        context=_context(),
        upstream_result=upstream,
        scenarios=scenarios,
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("source")),
    )


def test_authority_and_schema_metadata_are_locked() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["dossierSha256"] == M2206_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M2206_DOSSIER_SLICE
        assert metadata["unsupportedToNegative"] is False


def test_complete_surface_and_request_are_closed() -> None:
    surface = _surface()
    request = _request()
    assert {scenario.kind for scenario in surface.scenarios} == set(ChallengeKind)
    assert result_identifier(request).startswith("result.")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RobustnessObservation(
            observation_id="observation.invalid.bounds",
            scenario_id="scenario.m2206.0",
            metric="metric",
            baseline_value=1.0,
            challenged_value=0.5,
            envelope_lower=2.0,
            envelope_upper=1.0,
            within_envelope=False,
            ood_score=0.2,
            ood_band=OODBand.BORDERLINE,
            disposition=ChallengeDisposition.REVIEW_REQUIRED,
            evidence=(_evidence("invalid-bounds"),),
        ),
        lambda: RobustnessObservation(
            observation_id="observation.invalid.disposition",
            scenario_id="scenario.m2206.0",
            metric="metric",
            baseline_value=1.0,
            challenged_value=1.0,
            within_envelope=False,
            ood_score=0.2,
            ood_band=OODBand.IN_DOMAIN,
            disposition=ChallengeDisposition.WITHIN_ENVELOPE,
            evidence=(_evidence("invalid-disposition"),),
        ),
    ],
)
def test_observation_invariants_reject_inconsistent_values(factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match=r"robustness|within-envelope"):
        factory()


def test_request_binding_rejects_context_and_source_tampering() -> None:
    request = _request()
    changed_context = request.model_dump(mode="python")
    changed_context["context"] = _context("request.m2206.other")
    with pytest.raises(ValueError, match="context must bind"):
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(changed_context)
    missing_upstream = request.model_dump(mode="python")
    missing_upstream["source_artifacts"] = (_artifact("source-only"),)
    with pytest.raises(ValueError, match="include M22-05"):
        ChallengeProteinRnaDiscordanceRobustnessRequest.model_validate(missing_upstream)


def test_surface_requires_all_configured_kinds_and_observation_closure() -> None:
    surface = _surface()
    changed_surface = surface.model_dump(mode="python")
    changed_surface["scenarios"] = surface.scenarios[:-1]
    changed_surface["observations"] = surface.observations[:-1]
    with pytest.raises(ValueError, match="every configured"):
        RobustnessSurface.model_validate(changed_surface)
    missing_observation = surface.model_dump(mode="python")
    missing_observation["observations"] = surface.observations[:-1]
    with pytest.raises(ValueError, match="every scenario"):
        RobustnessSurface.model_validate(missing_observation)
