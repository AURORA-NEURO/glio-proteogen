"""Cross-contract closure checks for provisional robustness surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

import pytest

if TYPE_CHECKING:
    from enum import StrEnum

    from pydantic import BaseModel

from glio_proteogen.contracts.m24_06 import v1 as m2406
from glio_proteogen.contracts.m25_06 import v1 as m2506
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


class _RobustnessContract(Protocol):
    ChallengeKind: type[StrEnum]
    ChallengeDisposition: type[StrEnum]
    ChallengeSeverity: type[StrEnum]
    OODBand: type[StrEnum]
    ChallengeScenario: type[BaseModel]
    RobustnessObservation: type[BaseModel]
    RobustnessConfiguration: type[BaseModel]
    RobustnessSurface: type[BaseModel]


def _artifact(prefix: str, name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{prefix}.{name}",
        version="1.0.0",
        digest=sha256_digest(f"{prefix}:{name}"),
        media_type="application/json",
    )


def _evidence(prefix: str, name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(prefix, name),
        role="evidence",
        claim=f"Caller-declared {prefix} evidence.",
    )


def _context(prefix: str, request_id: str) -> ExecutionContext:
    evidence = _artifact(prefix, "control")
    accepted = UpstreamDecisionReference(
        decision_id=f"decision.{prefix}.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id=f"actor.{prefix}",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id=f"decision.{prefix}.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest(f"{prefix}.identity"),
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id=f"decision.{prefix}.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _surface(module: _RobustnessContract, prefix: str) -> BaseModel:
    kinds = tuple(module.ChallengeKind)
    configuration = module.RobustnessConfiguration(
        configuration_id=f"configuration.{prefix}",
        version="1.0.0",
        required_challenge_kinds=kinds,
        ood_threshold=0.8,
        evidence=(_evidence(prefix, "configuration"),),
    )
    scenarios = tuple(
        module.ChallengeScenario(
            scenario_id=f"scenario.{prefix}.{index}",
            kind=kind,
            severity=module.ChallengeSeverity.ROUTINE,
            perturbation=f"locked {kind.value} perturbation",
            expected_disposition=module.ChallengeDisposition.WITHIN_ENVELOPE,
            source_artifacts=(_artifact(prefix, f"scenario-{index}"),),
            evidence=(_evidence(prefix, f"scenario-evidence-{index}"),),
        )
        for index, kind in enumerate(kinds)
    )
    observations = tuple(
        module.RobustnessObservation(
            observation_id=f"observation.{prefix}.{index}",
            scenario_id=scenario.scenario_id,
            metric="robustness_delta",
            baseline_value=1.0,
            challenged_value=0.95,
            envelope_lower=0.8,
            envelope_upper=1.2,
            within_envelope=True,
            ood_score=0.1,
            ood_band=module.OODBand.IN_DOMAIN,
            disposition=module.ChallengeDisposition.WITHIN_ENVELOPE,
            evidence=(_evidence(prefix, f"observation-evidence-{index}"),),
        )
        for index, scenario in enumerate(scenarios)
    )
    return module.RobustnessSurface(
        surface_id=f"surface.{prefix}",
        version="1.0.0",
        scenarios=scenarios,
        observations=observations,
        configuration=configuration,
        evidence=(_evidence(prefix, "surface"),),
    )


@pytest.mark.parametrize(
    ("module", "prefix"),
    [(m2406, "m2406"), (m2506, "m2506")],
)
def test_robustness_surface_requires_configured_kinds_and_observation_closure(
    module: _RobustnessContract,
    prefix: str,
) -> None:
    surface = _surface(module, prefix)

    missing_kind = surface.model_dump(mode="python")
    missing_kind["scenarios"] = surface.scenarios[:-1]
    missing_kind["observations"] = surface.observations[:-1]
    with pytest.raises(ValueError, match="every configured"):
        module.RobustnessSurface.model_validate(missing_kind)

    missing_observation = surface.model_dump(mode="python")
    missing_observation["observations"] = surface.observations[:-1]
    with pytest.raises(ValueError, match="every scenario"):
        module.RobustnessSurface.model_validate(missing_observation)


@pytest.mark.parametrize(
    ("module", "prefix", "request_name", "upstream_name"),
    [
        (
            m2406,
            "m2406",
            "ChallengeBiomarkerPanelRobustnessRequest",
            "M2406_M2405_INPUT_MEDIA_TYPE",
        ),
        (
            m2506,
            "m2506",
            "ChallengeProteotypeRobustnessRequest",
            "M2506_M2505_INPUT_MEDIA_TYPE",
        ),
    ],
)
def test_robustness_request_requires_locked_challenge_coverage(
    module: _RobustnessContract,
    prefix: str,
    request_name: str,
    upstream_name: str,
) -> None:
    surface = _surface(module, prefix)
    request_type = getattr(module, request_name)
    request_id = f"request.{prefix}"
    upstream = _artifact(prefix, "upstream")
    request = request_type(
        request_id=request_id,
        context=_context(prefix, request_id),
        upstream_result=upstream.model_copy(
            update={"media_type": getattr(module, upstream_name)}
        ),
        scenarios=surface.scenarios,
        configuration=surface.configuration,
        source_artifacts=(upstream,),
    )
    changed = request.model_dump(mode="python")
    changed["scenarios"] = surface.scenarios[:-1]

    with pytest.raises(ValueError, match="locked challenge configuration"):
        request_type.model_validate(changed)


@pytest.mark.parametrize(
    ("module", "prefix"),
    [(m2406, "m2406"), (m2506, "m2506")],
)
def test_robustness_surface_rejects_disposition_and_ood_mismatch(
    module: _RobustnessContract,
    prefix: str,
) -> None:
    surface = _surface(module, prefix)
    disposition_mismatch = surface.model_dump(mode="python")
    disposition_observations = list(disposition_mismatch["observations"])
    disposition_observations[0]["disposition"] = module.ChallengeDisposition.REVIEW_REQUIRED
    disposition_mismatch["observations"] = tuple(disposition_observations)
    with pytest.raises(ValueError, match="disposition must match"):
        module.RobustnessSurface.model_validate(disposition_mismatch)

    ood_mismatch = surface.model_dump(mode="python")
    ood_observations = list(ood_mismatch["observations"])
    ood_observations[0]["ood_band"] = module.OODBand.OUT_OF_DOMAIN
    ood_mismatch["observations"] = tuple(ood_observations)
    with pytest.raises(ValueError, match="supported OOD bands"):
        module.RobustnessSurface.model_validate(ood_mismatch)

    unsupported_mismatch = surface.model_dump(mode="python")
    unsupported_scenarios = list(unsupported_mismatch["scenarios"])
    unsupported_scenarios[0]["expected_disposition"] = (
        module.ChallengeDisposition.ABSTAIN_UNSUPPORTED
    )
    unsupported_observations = list(unsupported_mismatch["observations"])
    unsupported_observations[0]["disposition"] = module.ChallengeDisposition.ABSTAIN_UNSUPPORTED
    unsupported_observations[0]["ood_band"] = module.OODBand.IN_DOMAIN
    unsupported_mismatch["scenarios"] = tuple(unsupported_scenarios)
    unsupported_mismatch["observations"] = tuple(unsupported_observations)
    with pytest.raises(ValueError, match="unsupported observations"):
        module.RobustnessSurface.model_validate(unsupported_mismatch)
