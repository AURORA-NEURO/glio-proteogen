"""Deterministic C02 identification harmonization with an upstream exclusion firewall."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_06 import (
    M0206_AUTHORITY_LIMITATION_CODE,
    M0206_AUTHORITY_LIMITATION_STATEMENT,
    M0206_CONTRACT_VERSION,
    M0206_HARMONIZATION_LIMITATION_CODE,
    M0206_HARMONIZATION_LIMITATION_STATEMENT,
    M0206_MODULE_ID,
    M0206_PROFILE_EVIDENCE_CLAIM,
    M0206_SENSITIVITY_NOTES,
    M0206_UNCERTAINTY_RATIONALES,
    AppliedStageAdjustment,
    BiologicalControlInvariant,
    BiologicalInvariantDiagnostic,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationValueState,
    HarmonizedIdentificationValue,
    HarmonizeIdentificationEvidenceRequest,
    IdentificationAbundanceObservation,
    IdentificationHarmonizationPolicy,
    IdentificationHarmonizationProfile,
    IdentificationHarmonizationResult,
    IdentificationLevelShift,
    IdentificationNormalizationStage,
    IdentificationStageTransformation,
    IdentificationTransformationManifest,
    ShiftState,
    SourceObservationSummary,
    TechnicalEffectDiagnostic,
    UpstreamHarmonizationReceipt,
    canonical_request_digest,
    configuration_digest,
    context_digest,
    observation_digest,
    policy_digest,
    prerequisites_digest,
    profile_digest,
)
from glio_proteogen.contracts.m02_06.canonical import normalized_prerequisites
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.kernel import (
    NormalizationStage,
    ScalarValue,
    StageResult,
    ValueState,
    normalize,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeIdentificationEvidenceRequest)
_NO_ELIGIBLE_CONTROL_TARGET: Final = "_m0206.no-eligible-control"
_MINIMUM_ACTIVE_LEVELS: Final = 2
_LIMITATIONS: Final = (
    Limitation(
        code=M0206_HARMONIZATION_LIMITATION_CODE,
        statement=M0206_HARMONIZATION_LIMITATION_STATEMENT,
    ),
    Limitation(
        code=M0206_AUTHORITY_LIMITATION_CODE,
        statement=M0206_AUTHORITY_LIMITATION_STATEMENT,
    ),
)


class IdentificationHarmonizationAuthorizationError(ValueError):
    """Denied controls detected without traversing scientific payloads."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize identification harmonization")


@dataclass(frozen=True, slots=True)
class _StageExecution:
    """One sequential kernel call and its exact working-set digests."""

    configured: IdentificationNormalizationStage
    result: StageResult
    input_digest: str
    output_digest: str


@dataclass(frozen=True, slots=True)
class _Execution:
    """Internal normalization state before contract presentation."""

    values: tuple[ScalarValue, ...]
    stages: tuple[_StageExecution, ...]
    globally_abstained: bool


class M0206IdentificationHarmonizationEngine:
    """Orchestrate C02-specific prerequisites, exclusions, diagnostics, and presentation."""

    __slots__ = ()

    def harmonize(self, request: object) -> IdentificationHarmonizationResult:
        """Harmonize one authorized request after strict contract reconstruction."""

        preflight_identification_harmonization_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        execution = _execute(validated)
        return _present(validated, execution)


def harmonize_identification_evidence(request: object) -> IdentificationHarmonizationResult:
    """Public stateless entry point."""

    return M0206IdentificationHarmonizationEngine().harmonize(request)


def preflight_identification_harmonization_authorization(candidate: object) -> None:
    """Reject denied raw payloads before prerequisites or observations are touched."""

    if isinstance(candidate, HarmonizeIdentificationEvidenceRequest):
        context: object = candidate.context
    elif isinstance(candidate, Mapping):
        context = candidate.get("context")
    else:
        raise IdentificationHarmonizationAuthorizationError
    references = _member(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _member(_member(references, role), "state") != state for role, state in expected.items()
    ):
        raise IdentificationHarmonizationAuthorizationError


def _member(candidate: object, name: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _execute(request: HarmonizeIdentificationEvidenceRequest) -> _Execution:
    globally_abstained = _requires_global_abstention(request)
    working = _kernel_values(request)
    stages: list[_StageExecution] = []
    for configured in request.profile.stages:
        input_digest = sha256_digest(_kernel_value_payload(working))
        kernel_stage = _kernel_stage(
            request,
            configured,
            force_not_evaluable=globally_abstained,
        )
        normalized = normalize(working, (kernel_stage,))
        working = normalized.values
        stages.append(
            _StageExecution(
                configured=configured,
                result=normalized.stages[0],
                input_digest=input_digest,
                output_digest=sha256_digest(_kernel_value_payload(working)),
            )
        )
    return _Execution(working, tuple(stages), globally_abstained)


def _requires_global_abstention(request: HarmonizeIdentificationEvidenceRequest) -> bool:
    prerequisites = request.prerequisites
    upstream_accepted = (
        prerequisites.conformance.disposition.value == "conformant"
        and prerequisites.identity.disposition.value == "conformant"
        and prerequisites.ingestion.disposition.value == "accepted"
        and prerequisites.quality.disposition.value == "accepted"
    )
    has_review_target = bool(prerequisites.artifact_detection.exclusion_mask.review_target_ids)
    has_unsupported = any(item.state.value == "unsupported" for item in request.observations)
    return not upstream_accepted or has_review_target or has_unsupported


def _excluded_targets(request: HarmonizeIdentificationEvidenceRequest) -> frozenset[str]:
    return frozenset(request.prerequisites.artifact_detection.exclusion_mask.excluded_target_ids)


def _kernel_values(
    request: HarmonizeIdentificationEvidenceRequest,
) -> tuple[ScalarValue, ...]:
    excluded = _excluded_targets(request)
    return tuple(
        ScalarValue(
            target_id=item.target_id,
            feature_id=item.feature_id,
            state=ValueState.OBSERVED,
            value=cast("float", item.value),
        )
        for item in sorted(
            request.observations,
            key=lambda value: (value.target_id, value.feature_id),
        )
        if item.target_id not in excluded and item.state.value == "observed"
    )


def _kernel_stage(
    request: HarmonizeIdentificationEvidenceRequest,
    configured: IdentificationNormalizationStage,
    *,
    force_not_evaluable: bool,
) -> NormalizationStage:
    excluded = _excluded_targets(request)
    active_levels_by_target = {
        item.target_id: next(
            level.level_id for level in item.factor_levels if level.factor is configured.factor
        )
        for item in request.observations
        if item.target_id not in excluded
    }
    active_levels = set(active_levels_by_target.values())
    insufficient_active_levels = (
        configured.reference_level_id not in active_levels
        or len(active_levels) < _MINIMUM_ACTIVE_LEVELS
    )
    levels = (
        {
            item.target_id: next(
                level.level_id for level in item.factor_levels if level.factor is configured.factor
            )
            for item in request.observations
        }
        if insufficient_active_levels
        else active_levels_by_target
    )
    control_targets = tuple(
        target_id for target_id in configured.control_target_ids if target_id not in excluded
    )
    if not control_targets:
        control_targets = (_NO_ELIGIBLE_CONTROL_TARGET,)
    stage_not_evaluable = force_not_evaluable or insufficient_active_levels
    minimum = (
        len(request.observations) + 1
        if stage_not_evaluable
        else request.policy.min_controls_per_level
    )
    return NormalizationStage(
        stage_id=configured.stage_id,
        factor_id=configured.factor.value,
        reference_level_id=configured.reference_level_id,
        control_feature_ids=configured.control_feature_ids,
        levels_by_target=levels,
        maximum_absolute_shift=request.policy.max_absolute_shift,
        minimum_control_observations=minimum,
        control_target_ids=control_targets,
    )


def _kernel_value_payload(values: tuple[ScalarValue, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "target_id": item.target_id,
            "feature_id": item.feature_id,
            "state": item.state.value,
            "value": item.value,
        }
        for item in sorted(values, key=lambda value: (value.target_id, value.feature_id))
    )


def _invariant_score(
    invariant: BiologicalControlInvariant,
    observations: tuple[IdentificationAbundanceObservation, ...],
    values: Mapping[tuple[str, str], float],
    excluded: frozenset[str],
) -> float | None:
    if invariant.kind.value == "direction":
        first = _member_median(
            observations,
            values,
            excluded,
            invariant.feature_ids[0],
            invariant.biological_group_ids[0],
        )
        second = _member_median(
            observations,
            values,
            excluded,
            invariant.feature_ids[0],
            invariant.biological_group_ids[1],
        )
    else:
        first = _member_median(
            observations,
            values,
            excluded,
            invariant.feature_ids[0],
            invariant.biological_group_ids[0],
        )
        second = _member_median(
            observations,
            values,
            excluded,
            invariant.feature_ids[1],
            invariant.biological_group_ids[0],
        )
    return None if first is None or second is None else second - first


def _member_median(
    observations: tuple[IdentificationAbundanceObservation, ...],
    values: Mapping[tuple[str, str], float],
    excluded: frozenset[str],
    feature_id: str,
    biological_group_id: str,
) -> float | None:
    members = tuple(
        item
        for item in observations
        if item.target_id not in excluded
        and item.feature_id == feature_id
        and item.biological_group_id == biological_group_id
    )
    if not members or any(item.state.value != "observed" for item in members):
        return None
    return statistics.median(values[(item.target_id, item.feature_id)] for item in members)


def _present(
    request: HarmonizeIdentificationEvidenceRequest,
    execution: _Execution,
) -> IdentificationHarmonizationResult:
    """Build the closed, privacy-minimized result from the exact sequential execution."""

    request_hash = canonical_request_digest(cast("Any", request))
    context_hash = context_digest(request.context)
    prerequisites_hash = prerequisites_digest(cast("Any", request.prerequisites))
    active_profile = _canonical_profile(request.profile)
    active_controls = tuple(sorted(request.biological_controls, key=canonical_json_bytes))
    profile_hash = profile_digest(active_profile)
    policy_hash = policy_digest(request.policy)
    configuration_hash = configuration_digest(
        active_profile,
        request.policy,
        active_controls,
    )
    unit = request.observations[0].unit
    transformations = _transformations(request, execution, unit)
    values = _values(request, execution, transformations)
    technical = _technical_diagnostics(request.policy, execution)
    biological = _biological_diagnostics(request, execution, active_controls)
    statuses = tuple(item.status for item in technical) + tuple(item.status for item in biological)
    disposition = (
        HarmonizationDisposition.QUARANTINED
        if DiagnosticStatus.FAILED in statuses
        else HarmonizationDisposition.ABSTAINED
        if DiagnosticStatus.NOT_EVALUABLE in statuses
        else HarmonizationDisposition.ACCEPTED
    )
    receipts = tuple(
        UpstreamHarmonizationReceipt.model_construct(
            module_id=item["module_id"],
            result_digest=item["result_digest"],
            disposition=item["disposition"],
            evaluated_target_ids=tuple(item.get("evaluated_target_ids", ())),
            excluded_target_ids=tuple(item.get("excluded_target_ids", ())),
            review_target_ids=tuple(item.get("review_target_ids", ())),
        )
        for item in normalized_prerequisites(cast("Any", request.prerequisites))
    )
    controls = _control_records(request.context)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                context_hash,
                prerequisites_hash,
                profile_hash,
                policy_hash,
                configuration_hash,
                *(item.result_digest for item in receipts),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    suffix = request_hash.removeprefix("sha256:")
    references = request.context.references
    return IdentificationHarmonizationResult(
        harmonization_id=f"harmonization.m0206.{suffix}",
        request_digest=request_hash,
        context_digest=context_hash,
        prerequisites_digest=prerequisites_hash,
        upstream_receipts=receipts,
        profile=active_profile,
        profile_digest=profile_hash,
        policy=request.policy,
        policy_digest=policy_hash,
        biological_controls=active_controls,
        configuration_digest=configuration_hash,
        disposition=disposition,
        values=values,
        transformation_manifest=IdentificationTransformationManifest.model_construct(
            profile_digest=profile_hash,
            policy_digest=policy_hash,
            configuration_digest=configuration_hash,
            stages=transformations,
        ),
        technical_effect_diagnostics=technical,
        biological_invariant_diagnostics=biological,
        support=_support(disposition),
        uncertainty=_uncertainty(),
        provenance=ProvenanceRecord(
            activity_id=f"activity.m0206.{suffix}",
            actor_id=request.context.actor_id,
            module_id=M0206_MODULE_ID,
            module_version=M0206_CONTRACT_VERSION,
            generated_at=request.context.occurred_at,
            input_digests=input_digests,
            configuration_digest=configuration_hash,
            consent_decision_id=references.consent.decision_id,
            consent_state=references.consent.state,
            consent_policy_version=references.consent.policy_version,
            consent_evidence_digest=references.consent.evidence.digest,
            control_decisions=controls,
        ),
        evidence=_evidence(request, controls),
        limitations=_LIMITATIONS,
        human_review_required=disposition is not HarmonizationDisposition.ACCEPTED,
        completed_at=request.context.occurred_at,
        supersedes_result_digest=request.supersedes_result_digest,
    )


def _canonical_profile(
    profile: IdentificationHarmonizationProfile,
) -> IdentificationHarmonizationProfile:
    return profile.model_copy(
        update={
            "stages": tuple(
                stage.model_copy(
                    update={
                        "control_target_ids": tuple(sorted(stage.control_target_ids)),
                        "control_feature_ids": tuple(sorted(stage.control_feature_ids)),
                    }
                )
                for stage in profile.stages
            )
        }
    )


def _transformations(
    request: HarmonizeIdentificationEvidenceRequest,
    execution: _Execution,
    unit: Literal["log2_abundance"],
) -> tuple[IdentificationStageTransformation, ...]:
    excluded = _excluded_targets(request)
    return tuple(
        IdentificationStageTransformation.model_construct(
            stage_id=stage.configured.stage_id,
            ordinal=stage.configured.ordinal,
            factor=stage.configured.factor,
            reference_level_id=stage.configured.reference_level_id,
            control_target_ids=tuple(sorted(set(stage.configured.control_target_ids) - excluded)),
            control_feature_ids=tuple(sorted(stage.configured.control_feature_ids)),
            maximum_absolute_shift=request.policy.max_absolute_shift,
            level_shifts=tuple(
                IdentificationLevelShift.model_construct(
                    level_id=shift.level,
                    state=ShiftState(shift.state.value),
                    estimated_shift=shift.estimated_shift,
                    applied_shift=shift.applied_shift,
                    unit=unit,
                    control_count=shift.control_observation_count,
                )
                for shift in stage.result.level_shifts
            ),
            input_digest=stage.input_digest,
            output_digest=stage.output_digest,
        )
        for stage in execution.stages
    )


def _source_summary(observation: IdentificationAbundanceObservation) -> SourceObservationSummary:
    return SourceObservationSummary.model_construct(
        target_id=observation.target_id,
        feature_id=observation.feature_id,
        biological_group_id=observation.biological_group_id,
        state=observation.state,
        value=observation.value,
        censoring_limit=observation.censoring_limit,
        unit=observation.unit,
        factor_levels=tuple(sorted(observation.factor_levels, key=lambda item: item.factor.value)),
        evidence_digests=tuple(sorted(item.digest for item in observation.evidence)),
    )


def _values(
    request: HarmonizeIdentificationEvidenceRequest,
    execution: _Execution,
    transformations: tuple[IdentificationStageTransformation, ...],
) -> tuple[HarmonizedIdentificationValue, ...]:
    excluded = _excluded_targets(request)
    normalized = {
        (item.target_id, item.feature_id): cast("float", item.value) for item in execution.values
    }
    transformations_by_id = {item.stage_id: item for item in transformations}
    values: list[HarmonizedIdentificationValue] = []
    for observation in sorted(
        request.observations,
        key=lambda item: (item.target_id, item.feature_id),
    ):
        source = _source_summary(observation)
        is_excluded = observation.target_id in excluded
        is_observed = observation.state is HarmonizationValueState.OBSERVED
        levels = {item.factor: item.level_id for item in observation.factor_levels}
        adjustments: tuple[AppliedStageAdjustment, ...] = ()
        if is_observed and not is_excluded:
            built: list[AppliedStageAdjustment] = []
            for stage in request.profile.stages:
                transformed = transformations_by_id[stage.stage_id]
                level_id = levels[stage.factor]
                shift = next(item for item in transformed.level_shifts if item.level_id == level_id)
                if shift.applied_shift is not None:
                    built.append(
                        AppliedStageAdjustment.model_construct(
                            stage_id=stage.stage_id,
                            ordinal=stage.ordinal,
                            factor=stage.factor,
                            level_id=level_id,
                            shift=shift.applied_shift,
                            unit=observation.unit,
                        )
                    )
            adjustments = tuple(built)
        values.append(
            HarmonizedIdentificationValue.model_construct(
                sample_id=observation.target_id,
                feature_id=observation.feature_id,
                biological_group_id=observation.biological_group_id,
                input_state=observation.state,
                output_state=(
                    HarmonizationValueState.EXCLUDED if is_excluded else observation.state
                ),
                input_value=observation.value,
                harmonized_value=(
                    normalized[(observation.target_id, observation.feature_id)]
                    if is_observed and not is_excluded
                    else None
                ),
                input_censoring_limit=observation.censoring_limit,
                censoring_limit=(None if is_excluded else observation.censoring_limit),
                unit=observation.unit,
                source_observation_digest=observation_digest(observation),
                source_observation=source,
                applied_adjustments=adjustments,
            )
        )
    return tuple(values)


def _technical_diagnostics(
    policy: IdentificationHarmonizationPolicy,
    execution: _Execution,
) -> tuple[TechnicalEffectDiagnostic, ...]:
    diagnostics: list[TechnicalEffectDiagnostic] = []
    for stage in execution.stages:
        incomplete = any(item.state.value == "not_evaluable" for item in stage.result.level_shifts)
        before = None if incomplete else stage.result.pre_level_spread
        after = None if incomplete else stage.result.post_level_spread
        capped = any(item.state.value == "capped" for item in stage.result.level_shifts)
        status = (
            DiagnosticStatus.NOT_EVALUABLE
            if before is None or after is None
            else DiagnosticStatus.PASSED
            if not capped and after < before and after <= policy.technical_effect_tolerance
            else DiagnosticStatus.FAILED
        )
        diagnostics.append(
            TechnicalEffectDiagnostic.model_construct(
                stage_id=stage.configured.stage_id,
                factor=stage.configured.factor,
                before_spread=before,
                after_spread=after,
                tolerance=policy.technical_effect_tolerance,
                capped=capped,
                status=status,
            )
        )
    return tuple(diagnostics)


def _biological_diagnostics(
    request: HarmonizeIdentificationEvidenceRequest,
    execution: _Execution,
    invariants: tuple[BiologicalControlInvariant, ...],
) -> tuple[BiologicalInvariantDiagnostic, ...]:
    excluded = _excluded_targets(request)
    before_values = {
        (item.target_id, item.feature_id): cast("float", item.value)
        for item in request.observations
        if item.target_id not in excluded and item.state is HarmonizationValueState.OBSERVED
    }
    after_values = {
        (item.target_id, item.feature_id): cast("float", item.value) for item in execution.values
    }
    diagnostics: list[BiologicalInvariantDiagnostic] = []
    for invariant in invariants:
        before = (
            None
            if execution.globally_abstained
            else _invariant_score(invariant, request.observations, before_values, excluded)
        )
        after = (
            None
            if execution.globally_abstained
            else _invariant_score(invariant, request.observations, after_values, excluded)
        )
        status = (
            DiagnosticStatus.NOT_EVALUABLE
            if before is None or after is None
            else DiagnosticStatus.PASSED
            if _sign(before) == _sign(after)
            and _sign(before) != 0
            and abs(after - before) <= request.policy.biological_invariant_tolerance
            else DiagnosticStatus.FAILED
        )
        diagnostics.append(
            BiologicalInvariantDiagnostic.model_construct(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                before_score=before,
                after_score=after,
                tolerance=request.policy.biological_invariant_tolerance,
                status=status,
            )
        )
    return tuple(diagnostics)


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _support(disposition: HarmonizationDisposition) -> SupportDecision:
    status, reason, rationale = {
        HarmonizationDisposition.ACCEPTED: (
            SupportStatus.LIMITED,
            "identification_harmonization_accepted",
            "All configured technical and biological diagnostics passed.",
        ),
        HarmonizationDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identification_harmonization_quarantined",
            "At least one harmonization diagnostic failed and requires review.",
        ),
        HarmonizationDisposition.ABSTAINED: (
            SupportStatus.UNSUPPORTED,
            "identification_harmonization_abstained",
            "At least one harmonization diagnostic was not evaluable.",
        ),
    }[disposition]
    return SupportDecision(status=status, reason_code=reason, rationale=rationale)


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable(M0206_UNCERTAINTY_RATIONALES["measurement"]),
        sampling=_not_estimable(M0206_UNCERTAINTY_RATIONALES["sampling"]),
        parameter=_not_estimable(M0206_UNCERTAINTY_RATIONALES["parameter"]),
        model_form=_not_estimable(M0206_UNCERTAINTY_RATIONALES["model_form"]),
        identification=_not_estimable(M0206_UNCERTAINTY_RATIONALES["identification"]),
        support=_not_estimable(M0206_UNCERTAINTY_RATIONALES["support"]),
        transport=_not_estimable(M0206_UNCERTAINTY_RATIONALES["transport"]),
        sensitivity_notes=M0206_SENSITIVITY_NOTES,
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in values
    )


def _evidence(
    request: HarmonizeIdentificationEvidenceRequest,
    controls: tuple[ControlDecisionRecord, ...],
) -> tuple[EvidenceReference, ...]:
    references_by_digest = {
        item.digest: item
        for item in (
            request.context.references.approved_configuration.evidence,
            request.context.references.identity_lineage.evidence,
            request.context.references.provenance.evidence,
            request.context.references.consent.evidence,
            request.context.references.quality.evidence,
            request.context.references.support.evidence,
            request.context.references.intended_use.evidence,
        )
    }
    values = [
        EvidenceReference(
            reference=references_by_digest[item.evidence_digest],
            role="evidence",
            claim=f"Caller-declared {item.role.value} control; issuer is not authenticated.",
        )
        for item in controls
    ]
    values.append(
        EvidenceReference(
            reference=request.profile.evidence,
            role="evidence",
            claim=M0206_PROFILE_EVIDENCE_CLAIM,
        )
    )
    return tuple(sorted(values, key=canonical_json_bytes))


__all__ = [
    "IdentificationHarmonizationAuthorizationError",
    "M0206IdentificationHarmonizationEngine",
    "harmonize_identification_evidence",
    "preflight_identification_harmonization_authorization",
]
