"""Lifecycle, replay, and safe-failure tests for M07-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m07_02 import (
    M0702_M0701_RESULT_MEDIA_TYPE,
    ConstructProteotypeAnalysisRepresentationRequest,
    FeatureLineage,
    FeatureSpecification,
    RepresentationPolicy,
    RepresentationTransformation,
    RepresentationTransformationKind,
    RepresentationValueKind,
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
from glio_proteogen.modules.c07_copy_number.m07_02_representation_feature_constructor import (
    BuiltRepresentation,
    M0702RepresentationEngine,
    RepresentationAuthorizationError,
    RepresentationInputError,
    construct_proteotype_analysis_representation,
)
from glio_proteogen.modules.c07_copy_number.m07_02_representation_feature_constructor import (
    service as m0702_service,
)


def _artifact(
    label: str,
    char: str = "a",
    media_type: str = "application/json",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0702.{label}",
        version="1.0.0",
        digest=f"sha256:{char * 64}",
        media_type=media_type,
    )


def _accepted(label: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m0702.{label}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(label),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request.m0702.test",
        actor_id="actor.m0702.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0702.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=_artifact("identity", "b"),
            ),
            provenance=_accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.m0702.consent",
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
        ),
    )


def _request(*, field: str = "abundance") -> ConstructProteotypeAnalysisRepresentationRequest:
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
    return ConstructProteotypeAnalysisRepresentationRequest(
        request_id="request.m0702.test",
        context=_context(),
        formal_state_result=_artifact("formal-state", "f", M0702_M0701_RESULT_MEDIA_TYPE),
        feature_specs=(first, second),
        policy=RepresentationPolicy(
            policy_id="policy.m0702.test",
            version="1.0.0",
            scaling_method="locked-z-score",
            mask_policy="missing-values-abstain",
            covariates=("site", "platform"),
        ),
        source_artifacts=(_artifact("proteome", "1"), _artifact("genome", "2")),
    )


def test_representation_is_deterministic_and_lineage_complete() -> None:
    engine = M0702RepresentationEngine()
    first = engine.construct(_request())
    second = engine.construct(_request())
    assert first.result.status.value == "constructed"
    assert len(first.result.features) == len(_request().feature_specs)
    assert first.result.features[0].lineage.feature_id == "feature.abundance"
    assert first.canonical_bytes == second.canonical_bytes


def test_replay_accepts_canonical_and_rejects_tamper() -> None:
    engine = M0702RepresentationEngine()
    built = engine.construct(_request())
    assert engine.verify(built.result, built.canonical_bytes).verified
    tampered = built.canonical_bytes[:-1] + bytes([built.canonical_bytes[-1] ^ 1])
    rejected = engine.verify(built.result, tampered)
    assert rejected.verified is False
    assert rejected.result_digest is None


def test_leakage_token_abstains_without_features() -> None:
    built = M0702RepresentationEngine().construct(_request(field="outcome_label"))
    assert built.result.status.value == "abstained"
    assert built.result.features == ()
    assert built.result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert built.result.abstention_reason


def test_duplicate_source_artifacts_abstain_safely() -> None:
    request = _request()
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )
    built = M0702RepresentationEngine().construct(duplicate)
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
    with pytest.raises(RepresentationAuthorizationError):
        M0702RepresentationEngine().construct(denied)
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
    with pytest.raises(RepresentationAuthorizationError):
        M0702RepresentationEngine().construct(unresolved)


def test_service_wrapper_and_strict_boundary() -> None:
    request = _request()
    service = m0702_service.M0702Service()
    built = service.execute(request)
    wrapper = construct_proteotype_analysis_representation(request)
    assert built.canonical_bytes == wrapper.canonical_bytes
    assert service.verify(built.result, built.canonical_bytes).verified
    with pytest.raises((TypeError, ValueError)):
        service.construct(object())


def test_built_result_rejects_digest_and_noncanonical_bytes() -> None:
    built = M0702RepresentationEngine().construct(_request())
    with pytest.raises(RepresentationInputError, match="digest"):
        BuiltRepresentation(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            built.canonical_bytes,
        )
    with pytest.raises(RepresentationInputError, match="canonical"):
        BuiltRepresentation(built.result, built.canonical_bytes + b" ")


def test_invalid_and_non_bytes_replay_fail_closed() -> None:
    engine = M0702RepresentationEngine()
    assert engine.verify(object()).reason.value == "invalid_result"
    built = engine.construct(_request())
    replay = engine.verify(built.result, "not-bytes")  # type: ignore[arg-type]
    assert replay.verified is False
    assert replay.content_verified is False


def test_request_digest_and_result_digest_are_canonical() -> None:
    request = _request()
    built = M0702RepresentationEngine().construct(request)
    assert built.result.request_digest == canonical_request_digest(request)
    assert built.result.result_digest == result_payload_digest(built.result)
