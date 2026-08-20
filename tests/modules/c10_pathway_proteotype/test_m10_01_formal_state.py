"""Adversarial deterministic runtime tests for provisional M10-01."""

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m10_01 import (
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValue,
    ProteinRnaFeatureValueKind,
    ProteinRnaInvariant,
    ProteinRnaInvariantSeverity,
    ProteinRnaInvariantStatus,
    ProteinRnaMissingness,
    ProteinRnaValidationStatus,
    ValidateProteinRnaDiscordanceStateRequest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    M1001AuthorizationError,
    M1001FormalStateEngine,
    M1001Service,
)

_DIGEST = "sha256:" + ("1" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    refs = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
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
        intended_use=_decision("intended_use"),
    )
    return ExecutionContext(
        request_id="request.m10-01",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=refs,
    )


def _request(
    expression: str = "protein.ratio >= 0.5",
    state: ProteinRnaMissingness = ProteinRnaMissingness.OBSERVED,
    severity: ProteinRnaInvariantSeverity = ProteinRnaInvariantSeverity.ERROR,
) -> ValidateProteinRnaDiscordanceStateRequest:
    feature = ProteinRnaFeatureDefinition(
        feature_id="protein.ratio",
        version="1.0.0",
        value_kind=ProteinRnaFeatureValueKind.SCALAR,
        unit="ratio",
        allowed_missingness=(ProteinRnaMissingness.MISSING, ProteinRnaMissingness.OBSERVED),
        domain_lower=0.0,
        domain_upper=1.0,
    )
    invariant = ProteinRnaInvariant(
        invariant_id="invariant.ratio",
        expression=expression,
        severity=severity,
        feature_ids=(feature.feature_id,),
    )
    schema = FormalProteinRnaDiscordanceStateSchema(
        schema_id="schema.protein-rna",
        version="1.0.0",
        features=(feature,),
        invariants=(invariant,),
    )
    return ValidateProteinRnaDiscordanceStateRequest(
        request_id="request.m10-01",
        context=_context(),
        state_schema=schema,
        values=(
            ProteinRnaFeatureValue(
                feature_id=feature.feature_id,
                state=state,
                unit=feature.unit,
                scalar_value=0.75 if state is ProteinRnaMissingness.OBSERVED else None,
            ),
        ),
        source_artifacts=(_artifact("source.state"),),
    )


def test_valid_formal_state_is_deterministic_and_replayable() -> None:
    engine = M1001FormalStateEngine()
    first = engine.execute(_request())
    second = engine.execute(_request())

    assert first.result.status is ProteinRnaValidationStatus.VALID
    assert first.result.invariant_results[0].status is ProteinRnaInvariantStatus.SATISFIED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_replay_rejects_self_rehashed_invariant_mutation() -> None:
    engine = M1001FormalStateEngine()
    built = engine.execute(_request())
    invariant = built.result.invariant_results[0]
    forged_invariant = invariant.model_copy(update={"message": invariant.message + " forged"})
    forged = built.result.model_copy(
        update={"invariant_results": (forged_invariant, *built.result.invariant_results[1:])}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    verdict = engine.verify(forged, canonical_json_bytes(forged.model_dump(mode="json")))

    assert verdict.content_verified is True
    assert verdict.deterministic_verified is False
    assert verdict.verified is False
    assert verdict.result_digest is None


def test_hard_invariant_is_invalid_without_abstention() -> None:
    built = M1001Service().execute(_request("protein.ratio >= 0.9"))

    assert built.result.status is ProteinRnaValidationStatus.INVALID
    assert built.result.support_decision.status.value == "limited"
    assert built.result.invariant_results[0].status is ProteinRnaInvariantStatus.VIOLATED


def test_missing_feature_abstains_without_negative_conversion() -> None:
    built = M1001Service().execute(_request(state=ProteinRnaMissingness.MISSING))

    assert built.result.status is ProteinRnaValidationStatus.ABSTAINED
    assert built.result.support_decision.status.value == "review_required"
    assert built.result.invariant_results[0].status is ProteinRnaInvariantStatus.NOT_EVALUABLE


def test_soft_conflict_remains_visible_and_limited() -> None:
    built = M1001Service().execute(
        _request("protein.ratio >= 0.9", severity=ProteinRnaInvariantSeverity.WARNING)
    )

    assert built.result.status is ProteinRnaValidationStatus.VALID
    assert built.result.support_decision.status.value == "limited"
    assert built.result.invariant_results[0].status is ProteinRnaInvariantStatus.VIOLATED


def test_preflight_rejects_withheld_consent_before_execution() -> None:
    request = _request()
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": refs.model_copy(update={"consent": withheld})}
            )
        }
    )
    with pytest.raises(M1001AuthorizationError):
        M1001FormalStateEngine().execute(denied)


def test_tampered_replay_is_rejected() -> None:
    engine = M1001FormalStateEngine()
    built = engine.execute(_request())
    tampered = built.result.model_copy(update={"result_id": "result.forged"})

    verification = engine.verify(tampered, built.canonical_bytes)
    assert not verification.verified
    assert verification.reason.value in {"non_canonical", "digest_mismatch", "invalid_result"}
