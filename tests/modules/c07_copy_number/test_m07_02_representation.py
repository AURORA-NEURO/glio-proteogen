"""Lifecycle, replay, and safe-failure tests for M07-02."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m07_02 import (
    M0702_GLIOMA_MODEL_FAMILY,
    M0702_M0701_RESULT_MEDIA_TYPE,
    ConstructProteotypeAnalysisRepresentationRequest,
    ConstructProteotypeAnalysisRepresentationVerification,
    FeatureLineage,
    FeatureSpecification,
    GliomaCopyNumberEvidenceState,
    GliomaCopyNumberObservation,
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
    engine as m0702_engine,
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


def _typed_observations() -> tuple[GliomaCopyNumberObservation, ...]:
    return (
        GliomaCopyNumberObservation(
            observation_id="observation.m0702.egfr",
            feature_id="feature.abundance",
            gene="EGFR",
            chromosome="7",
            segment_start=55_000_000,
            segment_end=55_300_000,
            evidence_state=GliomaCopyNumberEvidenceState.OBSERVED,
            log2_ratio=0.85,
            standard_error=0.12,
            tumor_purity=0.72,
            minor_copy_number=1.0,
        ),
        GliomaCopyNumberObservation(
            observation_id="observation.m0702.met",
            feature_id="feature.abundance",
            gene="MET",
            chromosome="7",
            segment_start=116_000_000,
            segment_end=116_500_000,
            evidence_state=GliomaCopyNumberEvidenceState.OBSERVED,
            log2_ratio=0.42,
            standard_error=0.16,
            tumor_purity=0.72,
            minor_copy_number=0.7,
        ),
        GliomaCopyNumberObservation(
            observation_id="observation.m0702.cdkna",
            feature_id="feature.residual",
            gene="CDKN2A",
            chromosome="9",
            segment_start=21_900_000,
            segment_end=21_950_000,
            evidence_state=GliomaCopyNumberEvidenceState.LEFT_CENSORED,
            standard_error=0.18,
            tumor_purity=0.72,
            censoring_limit=-0.65,
        ),
    )


def test_representation_is_deterministic_and_lineage_complete() -> None:
    engine = M0702RepresentationEngine()
    first = engine.construct(_request())
    second = engine.construct(_request())
    assert first.result.status.value == "constructed"
    assert len(first.result.features) == len(_request().feature_specs)
    assert first.result.features[0].lineage.feature_id == "feature.abundance"
    assert first.canonical_bytes == second.canonical_bytes


def test_typed_glioma_copy_number_lane_is_purity_aware_and_replayable() -> None:
    request = _request().model_copy(
        update={"typed_observations": _typed_observations(), "bootstrap_replicates": 16}
    )
    engine = M0702RepresentationEngine()
    built = engine.construct(request)
    repeat = engine.construct(request)
    assert built.result.status.value == "constructed"
    assert built.result.model_family == M0702_GLIOMA_MODEL_FAMILY
    assert built.result.optimization_diagnostics[0].status.value == "converged"
    assert all(
        feature.model_family == M0702_GLIOMA_MODEL_FAMILY
        for feature in built.result.features
    )
    assert built.result.features[0].values[0] > 0.0
    assert built.canonical_bytes == repeat.canonical_bytes
    assert engine.verify(built.result, built.canonical_bytes).verified


def test_typed_initializer_projects_observed_center_to_censor_bound() -> None:
    observations = _typed_observations()
    observed = observations[0]
    censored = observations[2].model_copy(update={"feature_id": observed.feature_id})
    items = (observed, censored)
    targets = tuple(m0702_engine._typed_target(item) for item in items)
    initial = m0702_engine._initial_typed_feature_value(items, targets)
    assert initial == pytest.approx(targets[1])
    assert initial <= targets[1]


def test_typed_initializer_keeps_censor_only_fit_at_neutral_when_feasible() -> None:
    censored = _typed_observations()[2]
    items = (censored,)
    target = m0702_engine._typed_target(censored)
    initial = m0702_engine._initial_typed_feature_value(items, (target,))
    assert initial == pytest.approx(min(0.0, target))


def test_typed_censor_bound_does_not_create_amplification_or_residual_signal() -> None:
    feasible = _typed_observations()[2].model_copy(update={"censoring_limit": 0.45})
    fit = m0702_engine._fit_typed_feature((feasible,), max_iterations=32)
    channels, _stability, _discordance, _drivers = m0702_engine._typed_channels(
        (feasible,), fit, ()
    )

    assert fit.value == pytest.approx(0.0)
    assert fit.residuals == (0.0,)
    assert channels[1] == pytest.approx(0.0)
    assert channels[2] == pytest.approx(0.0)
    assert channels[3] == pytest.approx(0.0)


def test_typed_feature_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _typed_observations()[0]
    original = m0702_engine._typed_objective
    calls = 0
    first_candidate_call = 2

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == first_candidate_call else value

    monkeypatch.setattr(m0702_engine, "_typed_objective", objective)
    fit = m0702_engine._fit_typed_feature((item,), max_iterations=32)
    assert fit.convergence_gap <= m0702_engine._TYPED_TOLERANCE
    assert calls > first_candidate_call
    assert all(
        after <= before + m0702_engine._TYPED_OBJECTIVE_TOLERANCE
        for before, after in zip(fit.trace[:-1], fit.trace[1:], strict=True)
    )


def test_typed_censor_bound_below_deletion_threshold_is_directional_evidence() -> None:
    censored = _typed_observations()[2]
    fit = m0702_engine._fit_typed_feature((censored,), max_iterations=32)
    channels, _stability, _discordance, _drivers = m0702_engine._typed_channels(
        (censored,), fit, ()
    )

    assert channels[3] > 0.0


def test_typed_observation_order_and_purity_change_are_semantic() -> None:
    observations = _typed_observations()
    request = _request().model_copy(
        update={"typed_observations": observations, "bootstrap_replicates": 16}
    )
    reversed_request = request.model_copy(
        update={"typed_observations": tuple(reversed(observations))}
    )
    engine = M0702RepresentationEngine()
    assert (
        engine.construct(request).canonical_bytes
        == engine.construct(reversed_request).canonical_bytes
    )
    low_purity = observations[0].model_copy(update={"tumor_purity": 0.45})
    low_result = engine.construct(
        request.model_copy(update={"typed_observations": (low_purity, *observations[1:])})
    )
    high_result = engine.construct(request)
    assert low_result.result.features[0].values[0] > high_result.result.features[0].values[0]


def test_typed_missing_or_unsupported_evidence_abstains_without_values() -> None:
    missing = GliomaCopyNumberObservation(
        observation_id="observation.m0702.missing",
        feature_id="feature.abundance",
        gene="EGFR",
        chromosome="7",
        segment_start=55_000_000,
        segment_end=55_300_000,
        evidence_state=GliomaCopyNumberEvidenceState.MISSING,
        quality_weight=0.0,
    )
    result = M0702RepresentationEngine().construct(
        _request().model_copy(update={"typed_observations": (missing,)})
    )
    assert result.result.status.value == "abstained"
    assert not result.result.features
    assert "insufficient" in (result.result.abstention_reason or "")


def test_typed_observation_rejects_unresolved_or_duplicate_segments() -> None:
    observations = _typed_observations()
    with pytest.raises(ValueError, match="segments must be unique"):
        _request().model_copy(
            update={
                "typed_observations": (
                    observations[0],
                    observations[0].model_copy(
                        update={"observation_id": "observation.m0702.egfr-copy"}
                    ),
                )
            }
        ).request_is_bound()  # type: ignore[operator]
    with pytest.raises(ValueError, match="reference requested features"):
        _request().model_copy(
            update={
                "typed_observations": (
                    observations[0].model_copy(update={"feature_id": "feature.unknown"}),
                )
            }
        ).request_is_bound()  # type: ignore[operator]


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
        request.model_copy(
            update={"formal_state_result": _artifact("wrong")}
        ).request_is_bound()  # type: ignore[operator]
    with pytest.raises(ValueError, match="unique"):
        request.model_copy(
            update={"feature_specs": (request.feature_specs[0],) * 2}
        ).request_is_bound()  # type: ignore[operator]
    with pytest.raises(ValueError, match="duplicated"):
        request.model_copy(
            update={
                "source_artifacts": (*request.source_artifacts, request.formal_state_result)
            }
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
