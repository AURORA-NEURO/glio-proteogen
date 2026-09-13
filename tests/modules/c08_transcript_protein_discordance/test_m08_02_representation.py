"""Lifecycle, replay, deterministic-lineage, and safe-failure tests for M08-02."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

import pytest

from glio_proteogen.contracts.m08_02 import (
    M0802_M0801_RESULT_MEDIA_TYPE,
    ConstructTranscriptProteinRepresentationRequest,
    ConstructTranscriptProteinRepresentationVerification,
    FeatureLineage,
    FeatureSpecification,
    GliomaTranscriptProteinEvidenceState,
    GliomaTranscriptProteinObservation,
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


def test_observed_values_use_declared_scaling_transform() -> None:
    request = _request()
    spec = request.feature_specs[0].model_copy(update={"source_values": (1.0, 2.0)})
    candidate = request.model_copy(
        update={"feature_specs": (spec, request.feature_specs[1])}
    )
    built = m0802.M0802RepresentationEngine().construct(candidate)
    assert built.result.status.value == "constructed"
    assert built.result.features[0].values == (-1.0, 1.0)


def test_observed_values_bind_the_declared_dimension_and_finiteness() -> None:
    spec = _request().feature_specs[0]
    with pytest.raises(ValueError, match="dimension"):
        type(spec).model_validate(
            spec.model_dump(mode="python") | {"source_values": (1.0,)},
            strict=True,
        )
    with pytest.raises(ValueError, match="finite"):
        type(spec).model_validate(
            spec.model_dump(mode="python") | {"source_values": (float("nan"), 1.0)},
            strict=True,
        )


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


def _typed_request(*, reverse: bool = False) -> ConstructTranscriptProteinRepresentationRequest:
    request = _request()
    observations = tuple(
        GliomaTranscriptProteinObservation(
            observation_id=f"observation.{feature_id}.{gene}",
            feature_id=feature_id,
            gene=gene,
            evidence_state=GliomaTranscriptProteinEvidenceState.OBSERVED,
            transcript_effect=transcript + offset,
            protein_effect=protein + offset / 2.0,
            transcript_standard_error=0.2,
            protein_standard_error=0.2,
            quality_weight=1.0,
        )
        for feature_id, transcript, protein in (
            ("feature.abundance", 1.2, 0.3),
            ("feature.residual", -0.6, -0.2),
        )
        for gene, offset in (
            ("EGFR", 0.0),
            ("MET", 0.05),
            ("PDGFRA", 0.1),
            ("PTEN", 0.15),
        )
    )
    return request.model_copy(
        update={"typed_observations": tuple(reversed(observations)) if reverse else observations}
    )


EXPECTED_TYPED_FEATURES = 2
EXPECTED_TYPED_GENES_PER_FEATURE = 4
FIRST_CANDIDATE_CALL = 2
NEGATIVE_TRANSCRIPT_LIMIT = -0.4
NEGATIVE_PROTEIN_LIMIT = -0.3
ROBUST_CENTER_MAX = 0.5
ARITHMETIC_MEAN_MIN = 1.0


def test_typed_glioma_discordance_is_evidence_driven_and_replay_bound() -> None:
    engine = m0802.M0802RepresentationEngine()
    first = engine.construct(_typed_request())
    repeat = engine.construct(_typed_request(reverse=True))

    assert first.result.status.value == "constructed"
    assert first.result.model_family == "glioma-transcript-protein-discordance-irls/1.0.0"
    assert len(first.result.optimization_diagnostics) == EXPECTED_TYPED_FEATURES
    assert all(
        item.status.value == "converged"
        for item in first.result.optimization_diagnostics
    )
    feature = first.result.features[0]
    assert feature.evidence_count == EXPECTED_TYPED_GENES_PER_FEATURE
    assert feature.lower_bound is not None
    assert feature.upper_bound is not None
    assert feature.lower_bound <= feature.values[0] <= feature.upper_bound
    assert feature.top_drivers
    assert feature.ablation_effects
    assert first.canonical_bytes == repeat.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_typed_pair_solver_backtracks_objective_increase(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    original = m0802.engine._typed_pair_objective
    calls = 0

    def objective(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        value = original(*args, **kwargs)
        return value + 100.0 if calls == FIRST_CANDIDATE_CALL else value

    monkeypatch.setattr(m0802.engine, "_typed_pair_objective", objective)
    fitted = m0802.engine._fit_typed_pair(
        _typed_request().typed_observations,
        max_iterations=64,
    )
    assert fitted is not None
    assert calls > FIRST_CANDIDATE_CALL
    assert all(
        after <= before + m0802.engine._TYPED_OBJECTIVE_TOLERANCE
        for before, after in pairwise(fitted[5])
    )


def test_typed_missing_evidence_abstains_without_negative_finding() -> None:
    request = _typed_request()
    missing = request.typed_observations[0].model_copy(
        update={
            "evidence_state": GliomaTranscriptProteinEvidenceState.MISSING,
            "transcript_effect": None,
            "protein_effect": None,
            "transcript_standard_error": None,
            "protein_standard_error": None,
            "quality_weight": 0.0,
        }
    )
    request = request.model_copy(
        update={"typed_observations": (missing, *request.typed_observations[1:])}
    )
    result = m0802.M0802RepresentationEngine().construct(request).result
    assert result.status.value == "constructed"
    assert result.features[0].evidence_count == EXPECTED_TYPED_GENES_PER_FEATURE - 1


def test_typed_left_censored_evidence_is_preserved_one_sided() -> None:
    request = _typed_request()
    censored = request.typed_observations[0].model_copy(
        update={
            "evidence_state": GliomaTranscriptProteinEvidenceState.LEFT_CENSORED,
            "transcript_effect": None,
            "protein_effect": None,
            "transcript_censoring_limit": -0.4,
            "protein_censoring_limit": -0.3,
        }
    )
    request = request.model_copy(
        update={"typed_observations": (censored, *request.typed_observations[1:])}
    )
    result = m0802.M0802RepresentationEngine().construct(request).result
    assert result.status.value == "constructed"
    assert result.features[0].evidence_count == EXPECTED_TYPED_GENES_PER_FEATURE
    assert result.features[0].lower_bound is not None
    assert result.features[0].upper_bound is not None


def test_typed_initial_state_uses_observed_center_and_censor_bound() -> None:
    request = _typed_request()
    censored = request.typed_observations[0].model_copy(
        update={
            "evidence_state": GliomaTranscriptProteinEvidenceState.LEFT_CENSORED,
            "transcript_effect": None,
            "protein_effect": None,
            "transcript_censoring_limit": -0.4,
            "protein_censoring_limit": -0.3,
        }
    )
    items = (censored, *request.typed_observations[1:4])
    transcript = m0802.engine._initial_typed_component_state(items, "transcript")
    protein = m0802.engine._initial_typed_component_state(items, "protein")
    assert transcript <= NEGATIVE_TRANSCRIPT_LIMIT
    assert protein <= NEGATIVE_PROTEIN_LIMIT


def test_typed_initial_component_center_downweights_failed_replicate() -> None:
    terms = (
        (0.2, 0.2, 1.0),
        (0.3, 0.2, 1.0),
        (4.0, 0.2, 1.0),
    )

    center = m0802.engine._robust_initial_component_center(terms)
    arithmetic_mean = sum(term[0] for term in terms) / len(terms)

    assert center < ROBUST_CENTER_MAX
    assert arithmetic_mean > ARITHMETIC_MEAN_MIN
    assert m0802.engine._initial_component_measurement_objective(center, terms) <= (
        m0802.engine._initial_component_measurement_objective(arithmetic_mean, terms)
    )


def test_censor_only_initial_state_stays_neutral_when_limit_is_positive() -> None:
    request = _typed_request()
    censored = request.typed_observations[0].model_copy(
        update={
            "evidence_state": GliomaTranscriptProteinEvidenceState.LEFT_CENSORED,
            "transcript_effect": None,
            "protein_effect": None,
            "transcript_censoring_limit": 0.4,
            "protein_censoring_limit": 0.3,
        }
    )
    assert m0802.engine._initial_typed_component_state(
        (censored,), "transcript"
    ) == pytest.approx(0.0)
    assert m0802.engine._initial_typed_component_state(
        (censored,), "protein"
    ) == pytest.approx(0.0)


def test_typed_duplicate_gene_and_unknown_feature_are_rejected() -> None:
    request = _typed_request()
    duplicate = request.typed_observations[0].model_copy(
        update={"observation_id": "observation.duplicate"}
    )
    duplicate_payload = request.model_dump(mode="python")
    duplicate_payload["typed_observations"] = (*request.typed_observations, duplicate)
    with pytest.raises(ValueError, match="unique per feature"):
        ConstructTranscriptProteinRepresentationRequest.model_validate(duplicate_payload)
    unknown = request.typed_observations[0].model_copy(update={"feature_id": "feature.unknown"})
    unknown_payload = request.model_dump(mode="python")
    unknown_payload["typed_observations"] = (unknown, *request.typed_observations[1:])
    with pytest.raises(ValueError, match="bind requested features"):
        ConstructTranscriptProteinRepresentationRequest.model_validate(unknown_payload)


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
