"""Lifecycle, safety, and deterministic replay tests for provisional M08-06."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_06 import (
    M0806_M0805_RESULT_MEDIA_TYPE,
    M0806_MAX_COMPONENTS,
    DecomposeTranscriptProteinUncertaintyRequest,
    GliomaUncertaintyProgram,
    SensitivityEnvelopeStatus,
    TypedUncertaintyEvidenceState,
    TypedUncertaintyObservation,
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
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    engine as m0806_engine,
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


def test_typed_glioma_uncertainty_decomposition_is_bootstrapped_and_replayable() -> None:
    request = _request().model_copy(
        update={
            "typed_observations": (
                TypedUncertaintyObservation(
                    observation_id="obs.egfr.rna",
                    feature_id="EGFR",
                    program=GliomaUncertaintyProgram.RTK_PI3K_AKT_MTOR,
                    modality="transcript",
                    effect=0.8,
                    standard_error=0.2,
                    quality_weight=0.95,
                ),
                TypedUncertaintyObservation(
                    observation_id="obs.egfr.protein",
                    feature_id="EGFR",
                    program=GliomaUncertaintyProgram.RTK_PI3K_AKT_MTOR,
                    modality="protein",
                    effect=1.1,
                    standard_error=0.25,
                    quality_weight=0.9,
                ),
                TypedUncertaintyObservation(
                    observation_id="obs.cdk4.protein",
                    feature_id="CDK4",
                    program=GliomaUncertaintyProgram.P53_CELL_CYCLE,
                    modality="protein",
                    effect=0.5,
                    standard_error=0.2,
                    quality_weight=0.85,
                ),
                TypedUncertaintyObservation(
                    observation_id="obs.tp53.site",
                    feature_id="TP53",
                    program=GliomaUncertaintyProgram.P53_CELL_CYCLE,
                    modality="phosphosite",
                    state=TypedUncertaintyEvidenceState.LEFT_CENSORED,
                    standard_error=0.3,
                    censoring_limit=0.0,
                    quality_weight=0.8,
                ),
            )
        }
    )
    engine = M0806UncertaintyDecompositionEngine()
    first = engine.decompose(request)
    reordered = engine.decompose(
        request.model_copy(
            update={"typed_observations": tuple(reversed(request.typed_observations))}
        )
    )

    assert first.status is UncertaintyDecompositionStatus.DECOMPOSED
    assert first.typed_model is True
    assert first.model_family == "glioma-uncertainty-decomposition-bootstrap/1.0.0"
    assert first.decomposition is not None
    assert len(first.decomposition.components) == M0806_MAX_COMPONENTS
    assert first.sensitivity_envelope.status is SensitivityEnvelopeStatus.EVALUATED
    assert first.uncertainty.measurement.state.value == "estimated"
    assert engine.verify(first).model_dump(mode="json") == first.model_dump(mode="json")
    assert reordered.model_dump(mode="json") == first.model_dump(mode="json")


def test_typed_glioma_uncertainty_abstains_for_insufficient_supported_evidence() -> None:
    request = _request().model_copy(
        update={
            "typed_observations": (
                TypedUncertaintyObservation(
                    observation_id="obs.missing",
                    feature_id="EGFR",
                    program=GliomaUncertaintyProgram.RTK_PI3K_AKT_MTOR,
                    modality="protein",
                    state=TypedUncertaintyEvidenceState.MISSING,
                    quality_weight=0.0,
                ),
            )
        }
    )
    result = M0806UncertaintyDecompositionEngine().decompose(request)

    assert result.status is UncertaintyDecompositionStatus.ABSTAINED
    assert result.typed_model is True
    assert result.decomposition is None
    assert result.sensitivity_envelope.status is SensitivityEnvelopeStatus.ABSTAINED


def test_typed_censor_only_location_stays_neutral_without_pseudo_target() -> None:
    censored = TypedUncertaintyObservation(
        observation_id="obs.censored.only",
        feature_id="EGFR",
        program=GliomaUncertaintyProgram.RTK_PI3K_AKT_MTOR,
        modality="protein",
        state=TypedUncertaintyEvidenceState.LEFT_CENSORED,
        standard_error=0.3,
        censoring_limit=0.4,
        quality_weight=0.8,
    )

    assert m0806_engine._typed_target(censored) == pytest.approx(0.4)
    assert m0806_engine._typed_robust_location((censored,)) == pytest.approx(0.0)
    assert m0806_engine._typed_robust_location(
        (censored,), {censored.observation_id: -1.0}
    ) == pytest.approx(-0.6)


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
