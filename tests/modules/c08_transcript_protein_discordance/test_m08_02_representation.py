"""Lifecycle, replay, deterministic-lineage, and safe-failure tests for M08-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_02 import (
    M0802_M0801_RESULT_MEDIA_TYPE,
    ConstructTranscriptProteinRepresentationRequest,
    ConstructTranscriptProteinRepresentationVerification,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheckStatus,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationReplayReason,
    RepresentationTransformation,
    RepresentationTransformationKind,
    RepresentationValueKind,
    TranscriptProteinRepresentationResult,
    canonical_request_digest,
    normalized_request,
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
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_02_representation_feature_constructor as m0802,
)


def _artifact(
    label: str,
    char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0802.{label}",
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0802.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(label),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0802.test",
        actor_id="actor.m0802.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0802.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0802.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent", "c"),
            ),
            quality=_accepted("quality"),
            support=_accepted("support"),
            intended_use=_accepted("intended-use"),
        ),
    )


def _lineage(feature_id: str, field: str, char: str) -> FeatureLineage:
    return FeatureLineage(
        feature_id=feature_id,
        source_artifacts=(_artifact(f"source-{field}", char),),
        source_fields=(field,),
        transformations=(
            RepresentationTransformation(
                sequence=1,
                kind=RepresentationTransformationKind.SCALING,
                name="locked-z-score",
                parameters_digest="sha256:" + "d" * 64,
            ),
            RepresentationTransformation(
                sequence=2,
                kind=RepresentationTransformationKind.MASKING,
                name="missing-values-mask",
                parameters_digest="sha256:" + "e" * 64,
            ),
        ),
    )


def _request(*, field: str = "abundance") -> ConstructTranscriptProteinRepresentationRequest:
    first = FeatureSpecification(
        feature_id="feature.abundance",
        version="1.0.0",
        value_kind=RepresentationValueKind.SCALAR,
        unit="normalized-abundance",
        dimension=2,
        lineage=_lineage("feature.abundance", field, "d"),
    )
    second = FeatureSpecification(
        feature_id="feature.residual",
        version="1.0.0",
        value_kind=RepresentationValueKind.VECTOR,
        unit="transcript-protein-residual",
        dimension=3,
        lineage=_lineage("feature.residual", "transcript_residual", "e"),
    )
    return ConstructTranscriptProteinRepresentationRequest(
        request_id="request.m0802.test",
        context=_context(),
        formal_state_result=_artifact("formal-state", "f", M0802_M0801_RESULT_MEDIA_TYPE),
        feature_specs=(first, second),
        policy=RepresentationPolicy(
            policy_id="policy.m0802.test",
            version="1.0.0",
            scaling_method="locked-z-score",
            mask_policy="missing-values-abstain",
            covariates=("site", "platform"),
            evidence=(
                # Reusing a source artifact as policy evidence is allowed and remains linked.
                # The digest is still included in the result provenance.
            ),
        ),
        source_artifacts=(_artifact("proteome", "1"), _artifact("genome", "2")),
    )


def test_representation_is_deterministic_and_lineage_complete() -> None:
    engine = m0802.M0802RepresentationEngine()
    first = engine.construct(_request())
    second = engine.construct(_request())
    assert first.result.status.value == "constructed"
    assert len(first.result.features) == len(_request().feature_specs)
    assert first.result.features[0].lineage.feature_id == "feature.abundance"
    assert first.result.features[0].lineage.leakage_safe is True
    assert first.canonical_bytes == second.canonical_bytes


def test_replay_accepts_canonical_and_rejects_tamper() -> None:
    engine = m0802.M0802RepresentationEngine()
    built = engine.construct(_request())
    assert engine.verify(built.result, built.canonical_bytes).verified
    tampered = built.canonical_bytes[:-1] + bytes([built.canonical_bytes[-1] ^ 1])
    rejected = engine.verify(built.result, tampered)
    assert rejected.verified is False
    assert rejected.result_digest is None
    assert rejected.reason is RepresentationReplayReason.CANONICAL_BYTES_MISMATCH


def test_leakage_token_abstains_without_features() -> None:
    built = m0802.M0802RepresentationEngine().construct(_request(field="outcome_label"))
    assert built.result.status.value == "abstained"
    assert built.result.features == ()
    assert built.result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert built.result.abstention_reason


def test_duplicate_source_artifacts_abstain_safely() -> None:
    request = _request()
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )
    built = m0802.M0802RepresentationEngine().construct(duplicate)
    assert built.result.status.value == "abstained"
    assert not built.result.features
    assert "unique" in (built.result.abstention_reason or "")


def test_authorization_checks_consent_identity_and_quality() -> None:
    request = _request()
    refs = request.context.references
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(m0802.RepresentationAuthorizationError):
        m0802.M0802RepresentationEngine().construct(denied)
    unresolved = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "identity_lineage": refs.identity_lineage.model_copy(
                                update={"state": IdentityLineageState.UNRESOLVED}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(m0802.RepresentationAuthorizationError):
        m0802.M0802RepresentationEngine().construct(unresolved)


def test_service_wrapper_and_strict_boundary() -> None:
    request = _request()
    service = m0802.service.M0802Service()
    built = service.execute(request)
    wrapper = m0802.construct_transcript_protein_representation(request)
    assert built.canonical_bytes == wrapper.canonical_bytes
    assert service.verify(built.result, built.canonical_bytes).verified
    with pytest.raises((TypeError, ValueError)):
        service.construct(object())


def test_built_result_rejects_digest_and_noncanonical_bytes() -> None:
    built = m0802.M0802RepresentationEngine().construct(_request())
    with pytest.raises(m0802.RepresentationInputError, match="digest"):
        m0802.BuiltRepresentation(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
    with pytest.raises(m0802.RepresentationInputError, match="canonical"):
        m0802.BuiltRepresentation(built.result, built.canonical_bytes + b" ")


def test_invalid_and_non_bytes_replay_fail_closed() -> None:
    engine = m0802.M0802RepresentationEngine()
    assert engine.verify(object()).reason.value == "invalid_result"
    built = engine.construct(_request())
    replay = engine.verify(built.result, "not-bytes")  # type: ignore[arg-type]
    assert replay.verified is False
    assert replay.content_verified is False


def test_request_digest_and_result_digest_are_canonical() -> None:
    request = _request()
    built = m0802.M0802RepresentationEngine().construct(request)
    assert built.result.request_digest == canonical_request_digest(request)
    assert built.result.result_digest == result_payload_digest(built.result)
    assert normalized_request(request.model_dump(mode="json")) == request.model_dump(mode="json")


def _result_variant(
    built: m0802.BuiltRepresentation,
    **updates: object,
) -> TranscriptProteinRepresentationResult:
    candidate = built.result.model_copy(update=updates)
    return TranscriptProteinRepresentationResult.model_validate(
        candidate.model_copy(update={"result_digest": result_payload_digest(candidate)}),
        strict=True,
    )


def test_result_closure_rejects_digest_coverage_leakage_and_support() -> None:
    built = m0802.M0802RepresentationEngine().construct(_request())
    with pytest.raises(ValueError, match="request digest"):
        TranscriptProteinRepresentationResult.model_validate(
            built.result.model_copy(update={"request_digest": "sha256:" + "0" * 64}),
            strict=True,
        )
    with pytest.raises(ValueError, match="requested feature specification"):
        _result_variant(built, features=built.result.features[:1])
    with pytest.raises(ValueError, match="leakage-safe support"):
        _result_variant(
            built,
            leakage_checks=(
                built.result.leakage_checks[0].model_copy(
                    update={"status": LeakageCheckStatus.FAILED}
                ),
                built.result.leakage_checks[1],
            ),
        )
    with pytest.raises(ValueError, match="leakage-safe support"):
        _result_variant(
            built,
            support_decision=SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="review",
                rationale="review required",
            ),
        )


def test_contract_lineage_and_replay_verification_are_closed() -> None:
    spec = _request().feature_specs[0]
    feature = RepresentationFeature(
        feature_id=spec.feature_id,
        value_kind=spec.value_kind,
        unit=spec.unit,
        values=(0.1, 0.2),
        lineage=spec.lineage,
    )
    with pytest.raises(ValueError, match="exact lineage"):
        RepresentationFeature.model_validate(
            feature.model_copy(
                update={"lineage": spec.lineage.model_copy(update={"feature_id": "other"})}
            ),
            strict=True,
        )
    with pytest.raises(ValueError, match="mask"):
        RepresentationFeature.model_validate(
            feature.model_copy(update={"mask": (True,)}), strict=True
        )
    first = spec.lineage.transformations[0]
    with pytest.raises(ValueError, match="unique ordered"):
        FeatureLineage.model_validate(
            spec.lineage.model_copy(update={"transformations": (first, first)}),
            strict=True,
        )
    digest = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="content and deterministic"):
        ConstructTranscriptProteinRepresentationVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=digest,
            reason=RepresentationReplayReason.VERIFIED,
        )


def test_contract_adversarial_closures_cover_unsafe_and_duplicate_paths() -> None:
    request = _request()
    spec = request.feature_specs[0]
    first = spec.lineage.transformations[0]
    unsafe_data = spec.lineage.model_dump(mode="python")
    unsafe_data["transformations"] = (first.model_copy(update={"leakage_safe": False}),)
    unsafe_lineage = FeatureLineage.model_construct(**unsafe_data)
    with pytest.raises(ValueError, match="leakage-unsafe"):
        unsafe_lineage.transformations_are_ordered()
    with pytest.raises(ValueError, match="duplicated"):
        request.model_copy(
            update={"source_artifacts": (*request.source_artifacts, request.formal_state_result)}
        ).request_is_bound()
    with pytest.raises(ValueError, match="unique"):
        request.model_copy(update={"feature_specs": (spec, spec)}).request_is_bound()
    with pytest.raises(ValueError, match="M08-01"):
        request.model_copy(
            update={"formal_state_result": request.source_artifacts[0]}
        ).request_is_bound()


def test_result_and_verification_fail_closed_on_duplicate_or_missing_digest() -> None:
    built = m0802.M0802RepresentationEngine().construct(_request())
    duplicate_features = (*built.result.features, built.result.features[0])
    candidate = built.result.model_copy(update={"features": duplicate_features})
    with pytest.raises(ValueError, match="feature ids"):
        candidate.result_is_closed()
    with pytest.raises(ValueError, match="leakage check ids"):
        built.result.model_copy(
            update={
                "leakage_checks": (
                    built.result.leakage_checks[0],
                    built.result.leakage_checks[0],
                )
            }
        ).result_is_closed()
    digest = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="trusted result digest"):
        ConstructTranscriptProteinRepresentationVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=digest,
            reason=RepresentationReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValueError, match="result digest"):
        ConstructTranscriptProteinRepresentationVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=RepresentationReplayReason.VERIFIED,
        )
