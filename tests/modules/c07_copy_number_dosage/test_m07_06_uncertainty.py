"""Lifecycle, replay, and authorization tests for provisional M07-06."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m07_06 import (
    M0706_CONSTRAINT_MEDIA_TYPE,
    DecomposeCopyNumberDosageUncertaintyRequest,
    UncertaintyDecompositionStatus,
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
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706AuthorizationError,
    M0706ReplayVerificationError,
    M0706Service,
    M0706UncertaintyDecompositionEngine,
    decompose_copy_number_dosage_uncertainty,
)


def _artifact(label: str, char: str = "a", media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=label,
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0706.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{label}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0706.test",
        actor_id="actor.m0706.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0706.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("evidence.identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0706.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _request() -> DecomposeCopyNumberDosageUncertaintyRequest:
    constraint = _artifact("constraint.m0705", "d", M0706_CONSTRAINT_MEDIA_TYPE)
    return DecomposeCopyNumberDosageUncertaintyRequest(
        request_id="request.m0706.test",
        context=_context(),
        constraint_result=constraint,
        policy={
            "policy_id": "policy.m0706.provisional",
            "version": "1.0.0",
            "method": "provisional-no-calibration",
            "calibration_reference": _artifact("calibration.m0706", "e"),
        },
        source_artifacts=(constraint, _artifact("source.proteome", "f")),
    )


def test_engine_abstains_with_complete_typed_uncertainty() -> None:
    first = M0706UncertaintyDecompositionEngine().decompose(_request())
    second = decompose_copy_number_dosage_uncertainty(_request())
    assert first.status is UncertaintyDecompositionStatus.ABSTAINED
    assert first.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert first.decomposition is None
    assert first.sensitivity_envelope.status.value == "abstained"
    assert first.uncertainty.transport.state.value == "not_estimable"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.request_digest == canonical_request_digest(first.request)
    assert first.result_digest == result_payload_digest(first)


def test_service_verify_replays_and_tamper_fails() -> None:
    service = M0706Service()
    result = service.execute(_request())
    assert service.verify(result).result_digest == result.result_digest
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    with pytest.raises(M0706ReplayVerificationError):
        service.verify(tampered, replay=False)


def test_request_rejects_missing_bound_constraint_and_duplicate_sources() -> None:
    request = _request()
    with pytest.raises(ValueError, match="include the bound constraint"):
        M0706Service.validate_request(
            request.model_copy(update={"source_artifacts": (_artifact("other", "1"),)})
        )
    with pytest.raises(ValueError, match="must not repeat"):
        M0706Service.validate_request(
            request.model_copy(
                update={
                    "source_artifacts": (
                        request.source_artifacts[0],
                        request.source_artifacts[0],
                    )
                }
            )
        )


def test_authorization_fails_closed_on_withheld_consent() -> None:
    request = _request()
    references = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": references.model_copy(
                        update={
                            "consent": references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(M0706AuthorizationError):
        M0706UncertaintyDecompositionEngine().decompose(denied)
