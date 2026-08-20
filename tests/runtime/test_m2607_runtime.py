"""Runtime, preflight, staged promotion, and replay tests for M26-07."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_07 import (
    ChangeClass,
    ChangeImpact,
    ChangeProposal,
    ChangeStatus,
    ControlProteinSubtypeChangeRequest,
    RevalidationRecord,
    RollbackPoint,
    RolloutStage,
    ShadowComparison,
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
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    M2607AuthorizationError,
    M2607ChangeControlService,
    M2607Plugin,
    M2607ReplayError,
    RollbackSubmission,
    preflight_m2607_authorization,
)


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _artifact(label: str, *, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _context(
    *, quality_state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
) -> ExecutionContext:
    def decision(
        role: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
    ) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m2607",
        actor_id="actor.platform-reviewer",
        occurred_at=datetime(2026, 8, 16, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality", quality_state),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _proposal() -> ChangeProposal:
    return ChangeProposal(
        proposal_id="proposal.m2607.1",
        current_version="1.0.0",
        proposed_version="1.1.0",
        change_class=ChangeClass.MINOR,
        impact=ChangeImpact.MODERATE,
        champion_digest=_digest("champion"),
        challenger_digest=_digest("challenger"),
        rationale="validate a bounded protein subtype change before staged promotion",
        required_revalidation_ids=("revalidation.m2607.required",),
        evidence=(
            EvidenceReference(
                reference=_artifact("proposal"),
                role="evidence",
                claim="change rationale evidence",
            ),
        ),
    )


def _request(
    *,
    context: ExecutionContext | None = None,
    revalidations: tuple[RevalidationRecord, ...] | None = None,
) -> ControlProteinSubtypeChangeRequest:
    proposal = _proposal()
    passed = RevalidationRecord(
        revalidation_id="revalidation.m2607.required",
        proposal_id=proposal.proposal_id,
        check_name="locked test and package verification",
        passed=True,
        report_digest=_digest("report"),
        completed_at=datetime(2026, 8, 16, 11, tzinfo=UTC),
        evidence=(),
    )
    comparison = ShadowComparison(
        comparison_id="comparison.m2607.error",
        proposal_id=proposal.proposal_id,
        metric_name="validation_error",
        champion_value=0.10,
        challenger_value=0.10,
        tolerance=0.01,
        no_regression=True,
        evidence=(),
    )
    rollback = RollbackPoint(
        rollback_id="rollback.m2607.1",
        target_version="1.0.0",
        restore_artifact=_artifact(
            "restore",
            media_type="application/vnd.glio-proteogen.restore+json",
        ),
        restore_command="restore-version 1.0.0",
        recovery_objective="return to the last accepted package within the recovery objective",
        evidence=(
            EvidenceReference(
                reference=_artifact("rollback-evidence"),
                role="evidence",
                claim="rollback smoke test evidence",
            ),
        ),
    )
    return ControlProteinSubtypeChangeRequest(
        request_id="request.m2607",
        context=context or _context(),
        proposal=proposal,
        revalidations=revalidations or (passed,),
        comparisons=(comparison,),
        rollback_point=rollback,
        source_artifacts=(
            _artifact("upstream-change"),
            _artifact("proposal"),
            _artifact("restore", media_type="application/vnd.glio-proteogen.restore+json"),
            _artifact("rollback-evidence"),
        ),
    )


def test_service_controls_staged_change_and_replays_deterministically() -> None:
    service = M2607ChangeControlService()
    request = _request()

    first = service.control(request)
    second = service.control(request)

    assert first.status is ChangeStatus.APPROVED
    assert first.change_package is not None
    assert first.change_package.rollout_stage is RolloutStage.STAGED
    assert first.change_package.approved_by == request.context.actor_id
    assert first.rollback_point == request.rollback_point
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).model_dump(mode="json") == first.model_dump(mode="json")


def test_failed_nonrequired_revalidation_abstains_without_package() -> None:
    request = _request(
        revalidations=(
            RevalidationRecord(
                revalidation_id="revalidation.m2607.required",
                proposal_id="proposal.m2607.1",
                check_name="locked test and package verification",
                passed=True,
                report_digest=_digest("report"),
                completed_at=datetime(2026, 8, 16, 11, tzinfo=UTC),
            ),
            RevalidationRecord(
                revalidation_id="revalidation.m2607.additional",
                proposal_id="proposal.m2607.1",
                check_name="additional review",
                passed=False,
                report_digest=_digest("failed-report"),
                completed_at=datetime(2026, 8, 16, 11, tzinfo=UTC),
            ),
        )
    )

    result = M2607ChangeControlService().control(request)

    assert result.status is ChangeStatus.ABSTAINED
    assert result.change_package is None
    assert result.rollback_point is None
    assert result.abstention_reason is not None
    assert any(finding.code.value == "revalidation_required" for finding in result.findings)


def test_failed_context_control_is_fail_closed() -> None:
    with pytest.raises(M2607AuthorizationError):
        M2607ChangeControlService().control(
            _request(context=_context(quality_state=UpstreamDecisionState.REJECTED))
        )


def test_replay_rejects_tampered_result_digest() -> None:
    result = M2607ChangeControlService().control(_request())
    tampered = result.model_copy(update={"result_digest": _digest("tampered")})

    with pytest.raises(M2607ReplayError):
        M2607ChangeControlService.verify(tampered)


def test_plugin_requires_token_and_preserves_json_parity() -> None:
    plugin = M2607Plugin()
    request = _request()
    token = plugin.validate(RollbackSubmission(request.model_dump_json()))
    result = plugin.run(token)

    assert result.status is ChangeStatus.APPROVED
    assert plugin.replay(result).result_digest == result.result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validated request token"):
        plugin.validate(request)  # type: ignore[arg-type]


def test_hostile_preflight_mapping_fails_closed() -> None:
    with pytest.raises(M2607AuthorizationError):
        preflight_m2607_authorization({"context": {"references": object()}})


def test_request_rejects_cross_proposal_comparison() -> None:
    request = _request()
    bad = request.comparisons[0].model_copy(update={"proposal_id": "proposal.other"})

    with pytest.raises(ValidationError, match="different proposal"):
        ControlProteinSubtypeChangeRequest.model_validate(
            request.model_dump(mode="python") | {"comparisons": (bad.model_dump(mode="python"),)}
        )
