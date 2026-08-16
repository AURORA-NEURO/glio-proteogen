"""Runtime, replay and capability tests for provisional M12-07."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m12_07 import (
    M1207_M1206_RESULT_MEDIA_TYPE,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
    PlausibilityGrade,
    UnresolvedConflict,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
    M1207PlausibilityAuthorizationError,
    M1207Plugin,
    M1207Service,
)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1207": label}),
        media_type=media_type,
    )


def _context(*, denied_role: str | None = None) -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=(
                UpstreamDecisionState.REJECTED
                if role == denied_role
                else UpstreamDecisionState.ACCEPTED
            ),
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m1207.runtime",
        actor_id="actor.m1207",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("approved_configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity_lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"subject": "one"}),
                evidence=_artifact("identity_lineage"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=(ConsentState.WITHHELD if denied_role == "consent" else ConsentState.GRANTED),
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended_use"),
        ),
    )


def _request(
    *,
    controls: tuple[PlausibilityControl, ...] | None = None,
    conflicts: tuple[UnresolvedConflict, ...] = (),
    context: ExecutionContext | None = None,
) -> AdjudicateBiomarkerPanelPlausibilityRequest:
    evidence = _artifact("control.evidence")
    if not controls:
        controls = tuple(
            PlausibilityControl(
                control_id=f"control.{kind.value}",
                kind=kind,
                criterion=f"{kind.value} criterion is satisfied.",
                declared_outcome=ControlOutcome.PASSED,
                required_evidence=(_evidence(f"{kind.value}.evidence", evidence),),
            )
            for kind in ControlKind
        )
    return AdjudicateBiomarkerPanelPlausibilityRequest(
        request_id="request.m1207.runtime",
        context=context or _context(),
        mechanism_inference_result=_artifact("mechanism", M1207_M1206_RESULT_MEDIA_TYPE),
        controls=controls,
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
        declared_conflicts=conflicts,
    )


def _evidence(label: str, reference: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(reference=reference, role="evidence", claim=f"Evidence {label}.")


def test_supported_adjudication_emits_high_grade_and_seven_uncertainties() -> None:
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(_request())

    assert result.status is PlausibilityAdjudicationStatus.ADJUDICATED
    assert result.grade is PlausibilityGrade.HIGH
    assert result.support_decision.status.value == "supported"
    assert result.human_review_required is False
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M12-07"
    assert result.uncertainty.model_form.probability == pytest.approx(0.2)
    assert len(result.evaluations) == len(ControlKind)


@pytest.mark.parametrize(
    "outcome",
    [ControlOutcome.FAILED, ControlOutcome.ABSTAINED, ControlOutcome.NOT_EVALUABLE],
)
def test_blocking_control_abstains_without_negative_finding(outcome: ControlOutcome) -> None:
    controls = list(_request().controls)
    controls[0] = controls[0].model_copy(update={"declared_outcome": outcome})
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(_request(controls=tuple(controls)))

    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.grade is None
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True
    assert result.findings


def test_direction_mismatch_is_hard_failure() -> None:
    controls = list(_request().controls)
    controls[0] = controls[0].model_copy(
        update={
            "expected_direction": "increasing",
            "declared_observed_direction": "decreasing",
        }
    )
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(_request(controls=tuple(controls)))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.evaluations[0].outcome is ControlOutcome.FAILED


def test_declared_conflict_remains_visible_and_requires_review() -> None:
    conflict = UnresolvedConflict(
        conflict_id="conflict.mechanism",
        description="Orthogonal evidence supports two mechanisms.",
        competing_mechanisms=("mechanism.a", "mechanism.b"),
        evidence=(_evidence("conflict", _artifact("conflict")),),
    )
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(_request(conflicts=(conflict,)))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.conflicts[0].conflict_id == "conflict.mechanism"
    assert any(item.code.value == "unresolved_conflict" for item in result.findings)


def test_denied_upstream_gate_fails_before_evidence_traversal() -> None:
    with pytest.raises(M1207PlausibilityAuthorizationError, match="quality"):
        M1207PlausibilityAdjudicatorEngine().adjudicate(
            _request(context=_context(denied_role="quality"))
        )


def test_replay_and_tamper_are_closed() -> None:
    engine = M1207PlausibilityAdjudicatorEngine()
    request = _request()
    result = engine.adjudicate(request)
    assert engine.verify(request, result).result_digest == result.result_digest
    tampered = result.model_copy(update={"grade": PlausibilityGrade.LOW})
    with pytest.raises(ValueError, match="result digest"):
        engine.verify(request, tampered)


def test_plugin_parses_once_and_binds_token_to_issuer() -> None:
    service = M1207Service()
    plugin = M1207Plugin(service)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-07"
    request = _request()
    token = plugin.validate(canonical_json_bytes(request.model_dump(mode="json")))
    assert plugin.run(token).result_id.startswith("result.m1207.")
    object_token = plugin.validate(request)
    assert plugin.run(object_token).result_id == plugin.run(token).result_id
    forged = token.__class__(request=token.request, issuer=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
