"""Lifecycle, safety, and deterministic replay tests for provisional M08-06."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_06 import (
    M0806_M0805_RESULT_MEDIA_TYPE,
    DecomposeTranscriptProteinUncertaintyRequest,
    SensitivityEnvelopeStatus,
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
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    M0806AuthorizationError,
    M0806Plugin,
    M0806ReplayVerificationError,
    M0806Service,
    M0806UncertaintyDecompositionEngine,
    decompose_transcript_protein_uncertainty,
)


def _artifact(
    label: str, char: str = "a", media_type: str = "application/json"
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=label,
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0806.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{label}"),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0806.test",
        actor_id="actor.m0806.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0806.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("evidence.identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0806.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _request() -> DecomposeTranscriptProteinUncertaintyRequest:
    estimator = _artifact("estimator.m0805", "d", M0806_M0805_RESULT_MEDIA_TYPE)
    return DecomposeTranscriptProteinUncertaintyRequest(
        request_id="request.m0806.test",
        context=_context(),
        estimator_result=estimator,
        policy={
            "policy_id": "policy.m0806.provisional",
            "version": "1.0.0",
            "method": "provisional-no-calibration",
            "calibration_reference": _artifact("calibration.m0806", "e"),
        },
        source_artifacts=(estimator, _artifact("source.proteome", "f")),
    )


def test_engine_abstains_with_all_seven_explicit_uncertainty_dimensions() -> None:
    first = M0806UncertaintyDecompositionEngine().decompose(_request())
    second = decompose_transcript_protein_uncertainty(_request())
    assert first.status is UncertaintyDecompositionStatus.ABSTAINED
    assert first.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert first.decomposition is None
    assert first.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED
    assert first.uncertainty.transport.state.value == "not_estimable"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.request_digest == canonical_request_digest(first.request)
    assert first.result_digest == result_payload_digest(first)


def test_service_verify_replays_and_tamper_fails() -> None:
    service = M0806Service()
    result = service.execute(_request())
    assert service.verify(result).result_digest == result.result_digest
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    with pytest.raises(M0806ReplayVerificationError):
        service.verify(tampered, replay=False)


def test_request_rejects_wrong_upstream_media_type() -> None:
    with pytest.raises(ValueError, match="must bind"):
        DecomposeTranscriptProteinUncertaintyRequest.model_validate(
            _request().model_dump(mode="python")
            | {"estimator_result": _artifact("wrong", "a", "application/json")},
            strict=True,
        )


def test_request_requires_bound_estimator_and_unique_sources() -> None:
    request = _request()
    with pytest.raises(ValueError, match="include the bound"):
        DecomposeTranscriptProteinUncertaintyRequest.model_validate(
            request.model_dump(mode="python") | {"source_artifacts": (_artifact("other", "1"),)},
            strict=True,
        )
    with pytest.raises(ValueError, match="must not repeat"):
        DecomposeTranscriptProteinUncertaintyRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.estimator_result, request.estimator_result)},
            strict=True,
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
    with pytest.raises(M0806AuthorizationError):
        M0806UncertaintyDecompositionEngine().decompose(denied)


def test_plugin_requires_issued_validate_token() -> None:
    plugin = M0806Plugin(M0806Service())
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"))
    token = plugin.validate(encoded)
    assert plugin.run(token).status is UncertaintyDecompositionStatus.ABSTAINED
    mapping_token = plugin.validate(request.model_dump(mode="json"))
    assert mapping_token.request == request
    assert plugin.run(mapping_token).status is UncertaintyDecompositionStatus.ABSTAINED
    assert plugin.run(plugin.validate(request)).status is UncertaintyDecompositionStatus.ABSTAINED
    verified = plugin.verify(M0806Service().execute(request))
    assert verified.status is UncertaintyDecompositionStatus.ABSTAINED
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(replace(token, _seal=object()))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_nested_request_is_immutable_and_strict() -> None:
    request = _request()
    with pytest.raises((TypeError, ValueError)):
        request.policy.method = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="request_id"):
        DecomposeTranscriptProteinUncertaintyRequest.model_validate(
            request.model_dump(mode="python") | {"request_id": 3},
            strict=True,
        )


def test_replay_rejects_plain_mapping_with_tampered_digest() -> None:
    result = M0806Service().execute(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(M0806ReplayVerificationError):
        M0806Service().verify(result)
