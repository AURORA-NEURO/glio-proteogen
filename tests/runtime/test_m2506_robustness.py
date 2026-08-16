"""Runtime and replay matrix for the provisional M25-06 challenge engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m25_06 import (
    M2506_M2504_INPUT_MEDIA_TYPE,
    ChallengeDisposition,
    ChallengeKind,
    ChallengeProteotypeRobustnessRequest,
    ChallengeScenario,
    ChallengeSeverity,
    RobustnessConfiguration,
    RobustnessStatus,
    contract_json_schema,
)
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
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    ChallengeSubmission,
    M2506AuthorizationError,
    M2506Plugin,
    M2506ReplayError,
    M2506RobustnessEngine,
    M2506Service,
)

_DIGEST = "sha256:" + "a" * 64
_CHALLENGE_KIND_COUNT = 8
_CONTROL_COUNT = 7


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _upstream() -> ArtifactReference:
    return _artifact("m2504-transport", M2506_M2504_INPUT_MEDIA_TYPE)


def _controls() -> ContextReferences:
    evidence = _artifact("control-evidence")
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=evidence,
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=evidence,
        ),
    )


def request(
    *,
    disposition: ChallengeDisposition = ChallengeDisposition.WITHIN_ENVELOPE,
    tamper_context: bool = False,
) -> ChallengeProteotypeRobustnessRequest:
    upstream = _upstream()
    scenarios = tuple(
        ChallengeScenario(
            scenario_id=f"scenario.{kind.value}",
            kind=kind,
            severity=ChallengeSeverity.ROUTINE,
            perturbation=f"locked perturbation for {kind.value}",
            expected_disposition=(
                disposition
                if kind is ChallengeKind.NOVEL_STATE
                else ChallengeDisposition.WITHIN_ENVELOPE
            ),
            source_artifacts=(upstream,),
            evidence=(
                EvidenceReference(
                    reference=upstream,
                    role="evidence",
                    claim="Caller-declared challenge evidence.",
                ),
            ),
        )
        for kind in ChallengeKind
    )
    configuration = RobustnessConfiguration(
        configuration_id="configuration.m2506",
        version="1.0.0",
        required_challenge_kinds=tuple(ChallengeKind),
        ood_threshold=0.5,
        evidence=(
            EvidenceReference(
                reference=upstream,
                role="evidence",
                claim="Locked challenge configuration.",
            ),
        ),
    )
    request_id = "request.m2506"
    context = ExecutionContext(
        request_id=("other.request" if tamper_context else request_id),
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=_controls(),
    )
    return ChallengeProteotypeRobustnessRequest(
        request_id=request_id,
        context=context,
        upstream_result=upstream,
        scenarios=scenarios,
        configuration=configuration,
        source_artifacts=(upstream,),
    )


def test_supported_eight_kind_matrix_is_deterministic_and_replayable() -> None:
    engine = M2506RobustnessEngine()
    first = engine.challenge(request())
    second = engine.challenge(request())
    assert first.status is RobustnessStatus.EVALUATED
    assert first.result_digest == second.result_digest
    assert first.result_id == second.result_id
    assert first.robustness_surface is not None
    assert len(first.robustness_surface.observations) == _CHALLENGE_KIND_COUNT
    assert engine.replay(first).result_digest == first.result_digest
    assert len(first.provenance.control_decisions) == _CONTROL_COUNT


def test_novel_state_abstains_with_safe_failure() -> None:
    result = M2506RobustnessEngine().challenge(
        request(disposition=ChallengeDisposition.ABSTAIN_UNSUPPORTED)
    )
    assert result.status is RobustnessStatus.ABSTAINED
    assert result.robustness_surface is None
    assert result.safe_failure_report is not None
    assert result.safe_failure_report.abstained is True
    assert result.support_decision.status.value == "review_required"


def test_reviewer_required_challenge_abstains_without_negative_finding() -> None:
    result = M2506RobustnessEngine().challenge(
        request(disposition=ChallengeDisposition.REVIEW_REQUIRED)
    )
    assert result.status is RobustnessStatus.ABSTAINED
    assert result.abstention_reason is not None
    assert all(item.code.value != "unsupported_perturbation" for item in result.findings)


def test_denied_control_fails_closed_before_contract_execution() -> None:
    candidate = request().model_dump(mode="python")
    candidate["context"]["references"]["consent"]["state"] = "revoked"
    with pytest.raises(M2506AuthorizationError):
        M2506RobustnessEngine().challenge(candidate)


def test_context_request_binding_is_closed() -> None:
    with pytest.raises(ValidationError):
        request(tamper_context=True)


def test_tampered_result_fails_replay() -> None:
    result = M2506RobustnessEngine().challenge(request())
    tampered: dict[str, Any] = result.model_dump(mode="python")
    tampered["result_digest"] = "sha256:" + "b" * 64
    with pytest.raises(M2506ReplayError):
        M2506RobustnessEngine().replay(tampered)  # type: ignore[arg-type]


def test_plugin_requires_submission_and_validated_token() -> None:
    service = M2506Service()
    plugin = M2506Plugin(service)
    with pytest.raises(TypeError):
        plugin.validate(request())
    validated = plugin.validate(ChallengeSubmission(request=request().model_dump(mode="json")))
    result = plugin.run(validated)
    assert result.status is RobustnessStatus.EVALUATED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M25-06"


def test_schema_has_closed_provisional_boundary() -> None:
    metadata = contract_json_schema("output")["x-glio-contract"]
    assert metadata["upstreamInputMediaType"] == M2506_M2504_INPUT_MEDIA_TYPE
    assert metadata["kinaseActivity"] is False
    assert metadata["externalContentTraversal"] is False
