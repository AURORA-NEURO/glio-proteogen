"""Lifecycle, replay, and safe-failure tests for M07-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m07_02 import (
    M0702_M0701_RESULT_MEDIA_TYPE,
    ConstructProteotypeAnalysisRepresentationRequest,
    ConstructProteotypeAnalysisRepresentationVerification,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheckStatus,
    ProteotypeAnalysisRepresentationResult,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationReplayReason,
    RepresentationTransformation,
    RepresentationTransformationKind,
    RepresentationValueKind,
    canonical_request_digest,
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
    SupportDecision,
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


def test_replay_rejects_self_rehashed_feature_mutation() -> None:
    engine = M0702RepresentationEngine()
    built = engine.construct(_request())
    feature = built.result.features[0]
    forged_feature = feature.model_copy(
        update={"values": (feature.values[0] + 0.25, *feature.values[1:])}
    )
    forged = built.result.model_copy(
        update={"features": (forged_feature, *built.result.features[1:])}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    outcome = engine.verify(forged, canonical_json_bytes(forged.model_dump(mode="json")))

    assert outcome.content_verified is True
    assert outcome.deterministic_verified is False
    assert outcome.verified is False


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


def _result_variant(
    built: BuiltRepresentation,
    **updates: object,
) -> ProteotypeAnalysisRepresentationResult:
    candidate = built.result.model_copy(update=updates)
    return ProteotypeAnalysisRepresentationResult.model_validate(
        candidate.model_copy(update={"result_digest": result_payload_digest(candidate)}),
        strict=True,
    )


def test_contract_lineage_specification_and_feature_shapes_are_closed() -> None:
    spec = _request().feature_specs[0]
    with pytest.raises(ValueError, match="exact lineage"):
        FeatureSpecification.model_validate(
            spec.model_copy(
                update={"lineage": spec.lineage.model_copy(update={"feature_id": "other"})}
            ),
            strict=True,
        )
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
    unsafe_data = spec.lineage.model_dump(mode="python")
    unsafe_data["transformations"] = (first.model_copy(update={"leakage_safe": False}),)
    unsafe = FeatureLineage.model_construct(**unsafe_data)
    with pytest.raises(ValueError, match="leakage-unsafe"):
        unsafe.transformations_are_ordered()  # type: ignore[operator]


def test_request_binding_rejects_wrong_handoff_duplicate_specs_and_source() -> None:
    request = _request()
    with pytest.raises(ValueError, match="M07-01"):
        request.model_copy(update={"formal_state_result": _artifact("wrong")}).request_is_bound()  # type: ignore[operator]
    with pytest.raises(ValueError, match="unique"):
        request.model_copy(
            update={"feature_specs": (request.feature_specs[0],) * 2}
        ).request_is_bound()  # type: ignore[operator]
    with pytest.raises(ValueError, match="duplicated"):
        request.model_copy(
            update={"source_artifacts": (*request.source_artifacts, request.formal_state_result)}
        ).request_is_bound()  # type: ignore[operator]


def test_result_closure_rejects_digest_coverage_leakage_and_support() -> None:
    built = M0702RepresentationEngine().construct(_request())
    with pytest.raises(ValueError, match="request digest"):
        ProteotypeAnalysisRepresentationResult.model_validate(
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
    with pytest.raises(ValueError, match="one leakage check"):
        _result_variant(built, leakage_checks=built.result.leakage_checks[:1])
    with pytest.raises(ValueError, match="check ids"):
        _result_variant(
            built,
            leakage_checks=(
                built.result.leakage_checks[0],
                built.result.leakage_checks[1],
                built.result.leakage_checks[0],
            ),
        )
    with pytest.raises(ValueError, match="canonical result content"):
        ProteotypeAnalysisRepresentationResult.model_validate(
            built.result.model_copy(update={"result_digest": "sha256:" + "0" * 64}),
            strict=True,
        )


def test_abstained_result_and_replay_verification_closure_are_fail_closed() -> None:
    abstained = M0702RepresentationEngine().construct(_request(field="outcome_label"))
    with pytest.raises(ValueError, match="safe status"):
        _result_variant(
            abstained,
            support_decision=SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="support",
                rationale="not safe",
            ),
        )
    digest = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="content and deterministic"):
        ConstructProteotypeAnalysisRepresentationVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=digest,
            reason=RepresentationReplayReason.VERIFIED,
        )
