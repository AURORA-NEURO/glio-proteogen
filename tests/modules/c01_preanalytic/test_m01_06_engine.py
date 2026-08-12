"""Focused qualification for the public M01-06 engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from glio_proteogen.contracts.m01_06 import (
    BiologicalInvariant,
    DiagnosticStatus,
    FactorLevel,
    HarmonizationDisposition,
    HarmonizationObservation,
    HarmonizationPolicy,
    HarmonizationProfile,
    HarmonizationStage,
    HarmonizeObservationsRequest,
    InvariantKind,
    LevelShift,
    ObservationState,
    ShiftState,
    StageTransformation,
    TechnicalFactor,
    TransformationManifest,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    M0106HarmonizationEngine,
    harmonize_observations,
)

_CONTROL_OBSERVATION_COUNT: Final = 2
_MAX_OBSERVATIONS: Final = 10_000
_MAX_RESULT_EVIDENCE: Final = 512


def _digest(label: str) -> str:
    return sha256_digest({"m0106": label})


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.{label}",
        version="1.0.0",
        digest=digest or _digest(label),
        media_type="application/json",
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.harmonize",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _observation(
    sample: str,
    feature: str,
    group: str,
    value: float | None,
    *,
    state: ObservationState = ObservationState.OBSERVED,
) -> HarmonizationObservation:
    return HarmonizationObservation(
        sample_id=sample,
        feature_id=feature,
        group_id=group,
        state=state,
        value=value,
        unit="log2_intensity",
        detection_limit=1.0 if state is ObservationState.BELOW_DETECTION_LIMIT else None,
        factor_levels=(
            FactorLevel(
                factor=TechnicalFactor.BATCH,
                level_id="batch.reference" if sample.endswith("a") else "batch.shifted",
            ),
        ),
        evidence=(_artifact(f"{sample}-{feature}"),),
    )


def _request(
    *,
    cap: float = 10.0,
    minimum: int = 1,
    tolerance: float = 0.0,
    observations: tuple[HarmonizationObservation, ...] | None = None,
    invariants: tuple[BiologicalInvariant, ...] = (),
) -> HarmonizeObservationsRequest:
    values = observations or (
        _observation("sample.a", "control", "group.one", 12.0),
        _observation("sample.a", "biology", "group.one", 7.0),
        _observation("sample.b", "control", "group.two", 8.0),
        _observation("sample.b", "biology", "group.two", 3.0),
    )
    profile = HarmonizationProfile(
        profile_id="profile.harmonize",
        version="1.0.0",
        stages=(
            HarmonizationStage(
                stage_id="stage.batch",
                ordinal=1,
                factor=TechnicalFactor.BATCH,
                reference_level_id="batch.reference",
                control_sample_ids=("sample.a", "sample.b"),
                control_feature_ids=("control",),
            ),
        ),
        evidence=_artifact("profile"),
    )
    policy = HarmonizationPolicy(
        policy_id="policy.harmonize",
        version="1.0.0",
        max_absolute_shift=cap,
        min_controls_per_level=minimum,
        technical_effect_tolerance=tolerance,
        biological_invariant_tolerance=tolerance,
    )
    return HarmonizeObservationsRequest(
        context=_context(configuration_digest(profile, policy, invariants)),
        profile=profile,
        policy=policy,
        observations=values,
        biological_invariants=invariants,
    )


def test_reference_shift_harmonizes_and_emits_replayable_manifest() -> None:
    request = _request()

    result = harmonize_observations(request)
    replay = M0106HarmonizationEngine().harmonize(request)

    assert replay == result
    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert tuple(item.value for item in result.values) == (7.0, 12.0, 7.0, 12.0)
    shifts = result.transformation_manifest.stages[0].level_shifts
    assert tuple(item.applied_shift for item in shifts) == (0.0, 4.0)
    assert shifts[0].state is ShiftState.ESTIMATED
    assert result.technical_effect_diagnostics[0].status is DiagnosticStatus.PASSED


def test_capped_shift_is_auditable_and_quarantined() -> None:
    result = harmonize_observations(_request(cap=2.0, tolerance=10.0))

    shifted = result.transformation_manifest.stages[0].level_shifts[1]
    assert shifted.state is ShiftState.CAPPED
    assert shifted.estimated_shift == pytest.approx(4.0)
    assert shifted.applied_shift == pytest.approx(2.0)
    assert result.technical_effect_diagnostics[0].capped is True
    assert result.disposition is HarmonizationDisposition.QUARANTINED


@pytest.mark.parametrize(
    "state",
    [ObservationState.MISSING, ObservationState.BELOW_DETECTION_LIMIT],
)
def test_nonobserved_value_is_preserved_and_never_lists_applied_stage(
    state: ObservationState,
) -> None:
    observations = (
        _observation("sample.a", "control", "group.one", 12.0),
        _observation("sample.a", "biology", "group.one", 7.0),
        _observation("sample.b", "control", "group.two", 8.0),
        _observation("sample.b", "biology", "group.two", None, state=state),
    )

    result = harmonize_observations(_request(observations=observations))
    absent = next(
        item
        for item in result.values
        if item.feature_id == "biology" and item.sample_id == "sample.b"
    )

    assert absent.state is state
    assert absent.value is None
    assert absent.applied_stage_ids == ()


def test_missing_reference_controls_yields_not_evaluable_quarantine() -> None:
    observations = (
        _observation("sample.a", "control", "group.one", None, state=ObservationState.MISSING),
        _observation("sample.a", "biology", "group.one", 7.0),
        _observation("sample.b", "control", "group.two", 8.0),
        _observation("sample.b", "biology", "group.two", 3.0),
    )

    result = harmonize_observations(_request(observations=observations))

    reference = result.transformation_manifest.stages[0].level_shifts[0]
    assert reference.state is ShiftState.NOT_EVALUABLE
    assert result.technical_effect_diagnostics[0].status is DiagnosticStatus.NOT_EVALUABLE
    assert result.disposition is HarmonizationDisposition.QUARANTINED


def test_any_incomplete_level_makes_whole_technical_stage_not_evaluable() -> None:
    observations = (
        _observation("sample.a", "control", "group.one", 12.0),
        _observation("sample.a", "biology", "group.one", 7.0),
        _observation("sample.b", "control", "group.two", None, state=ObservationState.MISSING),
        _observation("sample.b", "biology", "group.two", 3.0),
    )

    result = harmonize_observations(_request(observations=observations))

    diagnostic = result.technical_effect_diagnostics[0]
    assert diagnostic.before_spread is None
    assert diagnostic.after_spread is None
    assert diagnostic.status is DiagnosticStatus.NOT_EVALUABLE
    assert result.disposition is HarmonizationDisposition.QUARANTINED


def test_direction_invariant_is_checked_before_and_after() -> None:
    invariant = BiologicalInvariant(
        invariant_id="invariant.direction",
        kind=InvariantKind.DIRECTION,
        feature_ids=("biology",),
        group_ids=("group.one", "group.two"),
    )

    result = harmonize_observations(_request(invariants=(invariant,), tolerance=4.0))

    diagnostic = result.biological_invariant_diagnostics[0]
    assert diagnostic.before_score == pytest.approx(-4.0)
    assert diagnostic.after_score == pytest.approx(0.0)
    assert diagnostic.status is DiagnosticStatus.FAILED
    assert result.disposition is HarmonizationDisposition.QUARANTINED


def test_observation_order_does_not_change_result() -> None:
    request = _request()
    reversed_request = HarmonizeObservationsRequest(
        context=request.context,
        profile=request.profile,
        policy=request.policy,
        observations=tuple(reversed(request.observations)),
        biological_invariants=request.biological_invariants,
    )

    assert harmonize_observations(request) == harmonize_observations(reversed_request)


def test_transformation_manifest_requires_unique_stage_and_factor() -> None:
    result = harmonize_observations(_request())
    stage = result.transformation_manifest.stages[0]

    with pytest.raises(ValueError, match="identifiers must be unique"):
        TransformationManifest(
            profile_digest=result.profile_digest,
            policy_digest=result.policy_digest,
            configuration_digest=result.configuration_digest,
            stages=(stage, stage.model_copy(update={"ordinal": 2})),
        )


def test_manifest_binds_cap_and_rejects_forged_shift_arithmetic() -> None:
    result = harmonize_observations(_request(cap=2.0, tolerance=10.0))
    stage = result.transformation_manifest.stages[0]
    assert stage.maximum_absolute_shift == pytest.approx(2.0)
    forged = LevelShift(
        level_id="batch.shifted",
        state=ShiftState.CAPPED,
        estimated_shift=4.0,
        applied_shift=1.0,
        unit="log2_intensity",
        control_count=1,
    )

    with pytest.raises(ValueError, match="apply the declared cap exactly"):
        StageTransformation(
            stage_id=stage.stage_id,
            ordinal=stage.ordinal,
            factor=stage.factor,
            reference_level_id=stage.reference_level_id,
            maximum_absolute_shift=stage.maximum_absolute_shift,
            level_shifts=(stage.level_shifts[0], forged),
            input_digest=stage.input_digest,
            output_digest=stage.output_digest,
        )


def test_result_provenance_configuration_control_binds_result_digest() -> None:
    result = harmonize_observations(_request())
    approved = next(
        item
        for item in result.provenance.control_decisions
        if item.role.value == "approved_configuration"
    )

    assert approved.evidence_digest == result.configuration_digest


def test_result_rejects_mixed_output_and_shift_units() -> None:
    result = harmonize_observations(_request())
    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + ("0" * 64)
    payload["transformation_manifest"]["stages"][0]["level_shifts"][0]["unit"] = "other"

    with pytest.raises(ValueError, match="one common unit"):
        type(result).model_validate(payload, strict=True)


def test_exact_observation_cap_produces_closed_result() -> None:
    profile_request = _request()
    common_evidence = (_artifact("large-corpus"),)
    observations = tuple(
        HarmonizationObservation(
            sample_id=f"sample.{index:05d}",
            feature_id=(
                "control"
                if index < _CONTROL_OBSERVATION_COUNT
                else f"feature.{index:05d}"
            ),
            group_id="group.synthetic",
            state=ObservationState.OBSERVED,
            value=12.0 if index % 2 == 0 else 8.0,
            unit="log2_intensity",
            factor_levels=(
                FactorLevel(
                    factor=TechnicalFactor.BATCH,
                    level_id="batch.reference" if index % 2 == 0 else "batch.shifted",
                ),
            ),
            evidence=common_evidence,
        )
        for index in range(_MAX_OBSERVATIONS)
    )
    profile = HarmonizationProfile(
        profile_id=profile_request.profile.profile_id,
        version=profile_request.profile.version,
        stages=(
            HarmonizationStage(
                stage_id="stage.batch",
                ordinal=1,
                factor=TechnicalFactor.BATCH,
                reference_level_id="batch.reference",
                control_sample_ids=("sample.00000", "sample.00001"),
                control_feature_ids=("control",),
            ),
        ),
        evidence=profile_request.profile.evidence,
    )
    policy = profile_request.policy
    request = HarmonizeObservationsRequest(
        context=_context(configuration_digest(profile, policy, ())),
        profile=profile,
        policy=policy,
        observations=observations,
    )

    result = harmonize_observations(request)

    assert len(result.values) == _MAX_OBSERVATIONS
    assert len(result.provenance.input_digests) < _MAX_OBSERVATIONS
    assert len(result.evidence) <= _MAX_RESULT_EVIDENCE
