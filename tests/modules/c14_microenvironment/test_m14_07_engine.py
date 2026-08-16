"""M14-07 runtime, replay, authorization, and safety tests."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m14_07 import (
    M1407_M1404_RESULT_MEDIA_TYPE,
    AdjudicateProteinSubtypePlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityControl,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c14_microenvironment.m14_07_plausibility_negative_control_adjudicator import (  # noqa: E501
    M1407AuthorizationError,
    M1407InferenceError,
    M1407PlausibilityAdjudicator,
    M1407ReplayVerificationError,
    adjudicate_protein_subtype_plausibility,
    preflight_plausibility_authorization,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=sha256_digest({"m1407": label}),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M14-07 control evidence.",
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.UNRESOLVED
    consent = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.configuration",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.configuration"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity,
            policy_version="1.0.0",
            binding_digest=sha256_digest("identity"),
            evidence=_artifact("control.identity"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent,
            policy_version="1.0.0",
            evidence=_artifact("control.consent"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.quality"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.support"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision,
            policy_version="1.0.0",
            evidence=_artifact("control.intended"),
        ),
    )


def _request(
    *,
    accepted: bool = True,
    criterion: str = "consistent orthogonal evidence",
    missing_kind: bool = False,
) -> AdjudicateProteinSubtypePlausibilityRequest:
    kinds = tuple(ControlKind)
    controls = tuple(
        PlausibilityControl(
            control_id=f"control.{kind.value}",
            kind=kind,
            criterion=criterion
            if kind is ControlKind.KNOWN_CONTROL
            else f"consistent {kind.value}",
            expected_direction="consistent",
            required_evidence=(_evidence(f"control.{kind.value}"),),
        )
        for kind in (kinds[:-1] if missing_kind else kinds)
    )
    return AdjudicateProteinSubtypePlausibilityRequest(
        request_id="request.m1407",
        context=ExecutionContext(
            request_id="request.m1407",
            actor_id="actor.test",
            occurred_at=_WHEN,
            references=_controls(accepted=accepted),
        ),
        mechanism_inference_result=_artifact("mechanism", M1407_M1404_RESULT_MEDIA_TYPE),
        controls=controls,
        source_artifacts=(
            _artifact("proteome"),
            _artifact("genome"),
            _artifact("transcriptome"),
            _artifact("ptm"),
        ),
    )


def test_supported_adjudication_is_deterministic_and_replayable() -> None:
    engine = M1407PlausibilityAdjudicator()
    result = engine.infer(_request())
    assert result.status is PlausibilityAdjudicationStatus.ADJUDICATED
    assert result.grade is not None
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert len(result.evaluations) == len(tuple(ControlKind))
    assert result.uncertainty.measurement.probability == 0.9
    assert engine.verify(result) == result


@pytest.mark.parametrize(
    ("criterion", "expected"),
    [
        ("fail: assay incompatible", ControlOutcome.FAILED),
        ("unsupported signal", ControlOutcome.NOT_EVALUABLE),
        ("abstain pending review", ControlOutcome.ABSTAINED),
    ],
)
def test_blocking_control_outcomes_abstain(criterion: str, expected: ControlOutcome) -> None:
    result = M1407PlausibilityAdjudicator().infer(_request(criterion=criterion))
    assert result.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert result.grade is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required
    assert any(item.outcome is expected for item in result.evaluations)


def test_missing_control_and_conflict_are_visible_and_block_release() -> None:
    missing = M1407PlausibilityAdjudicator().infer(_request(missing_kind=True))
    assert missing.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert any(item.code.value == "control_not_evaluable" for item in missing.findings)
    conflict = M1407PlausibilityAdjudicator().infer(
        _request(criterion="conflict: primary vs alternate")
    )
    assert conflict.status is PlausibilityAdjudicationStatus.ABSTAINED
    assert conflict.conflicts
    assert any(item.code.value == "unresolved_conflict" for item in conflict.findings)


def test_authorization_and_hostile_object_fail_closed() -> None:
    with pytest.raises(M1407AuthorizationError):
        M1407PlausibilityAdjudicator().infer(_request(accepted=False))

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("must not traverse opaque content")

    with pytest.raises(M1407AuthorizationError):
        preflight_plausibility_authorization(Hostile())

    for malformed in (None, {"context": None}, {"context": {"references": None}}):
        with pytest.raises(M1407AuthorizationError):
            preflight_plausibility_authorization(malformed)
    malformed_mapping = _request().model_dump(mode="json")
    malformed_mapping["context"]["references"]["quality"] = {}
    with pytest.raises(M1407AuthorizationError):
        preflight_plausibility_authorization(malformed_mapping)


def test_inference_error_and_public_operation_are_safe() -> None:
    raw = _request().model_dump(mode="json")
    raw.pop("controls")
    with pytest.raises(M1407InferenceError):
        M1407PlausibilityAdjudicator().infer(raw)
    assert adjudicate_protein_subtype_plausibility(_request()).status.value == "adjudicated"


def test_verify_rejects_invalid_and_divergent_replays() -> None:
    engine = M1407PlausibilityAdjudicator()
    with pytest.raises(M1407ReplayVerificationError):
        engine.verify(object())
    result = engine.infer(_request())

    class Divergent(M1407PlausibilityAdjudicator):
        def infer(self, request: object):  # type: ignore[no-untyped-def]
            del request
            return super().infer(_request(criterion="fail: divergent"))

    with pytest.raises(M1407ReplayVerificationError):
        Divergent().verify(result)


def test_replay_tamper_and_canonical_bytes_are_rejected() -> None:
    engine = M1407PlausibilityAdjudicator()
    result = engine.infer(_request())
    assert canonical_json_bytes(result)
    with pytest.raises(M1407ReplayVerificationError):
        engine.verify(result.model_copy(update={"result_digest": sha256_digest("tampered")}))
    assert engine.verify(result, replay=False) == result


def test_duplicate_control_ids_are_rejected_by_contract() -> None:
    payload = _request().model_dump(mode="python")
    payload["controls"] = (payload["controls"][0], payload["controls"][0])
    with pytest.raises(ValueError, match="control ids"):
        AdjudicateProteinSubtypePlausibilityRequest.model_validate(payload, strict=True)
