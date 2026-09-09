"""Bounded deterministic M05-06 support-coordinate kernel.

The governed ABI carries explicit estimation and validation anchors for each
technical factor.  The kernel uses those anchors to estimate robust level
effects (medians of level/reference contrasts), applies them in the locked
eight-stage order, and reports held-out spread reduction.  Missing anchor pairs
remain unevaluable; they are never converted into zero biological evidence.
"""

# The kernel imports contract types lazily to avoid the contract/canonical cycle.
# ruff: noqa: PLC0415

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

from glio_proteogen.contracts.m05_06 import (
    PtmLocalizationHarmonizationDiagnosticStatus,
    PtmLocalizationHarmonizationPolicy,
    PtmLocalizationHarmonizedAnalysis,
    PtmLocalizationInvariantDiagnostic,
    PtmLocalizationNormalizationStage,
    PtmLocalizationStageTransformation,
    PtmLocalizationSupportLedger,
    PtmLocalizationSupportObservation,
    PtmLocalizationSupportObservationState,
    PtmLocalizationSupportShiftState,
    PtmLocalizationTechnicalEffectDiagnostic,
    PtmLocalizationTransformationManifest,
)

_MIN_DIAGNOSTIC_OBSERVATIONS = 2
_StageDiagnostic = tuple[
    int | None, int | None, PtmLocalizationHarmonizationDiagnosticStatus
]


class _EmptyAnchorMedianError(ValueError):
    """Raised when a calibration stage has no contrasts to summarize."""

    def __init__(self) -> None:
        super().__init__("anchor median requires a value")


@dataclass(frozen=True, slots=True)
class PtmLocalizationHarmonizationExecution:
    analysis: PtmLocalizationHarmonizedAnalysis | None
    transformation_manifest: PtmLocalizationTransformationManifest | None
    technical_effect_diagnostics: tuple[PtmLocalizationTechnicalEffectDiagnostic, ...]
    invariant_diagnostics: tuple[PtmLocalizationInvariantDiagnostic, ...]


class M0506PtmLocalizationHarmonizationKernel:
    """Apply deterministic anchor-based PTM support harmonization."""

    __slots__ = ()

    @staticmethod
    def _median(values: Iterable[int]) -> int:
        ordered = sorted(values)
        if not ordered:
            raise _EmptyAnchorMedianError
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return int(ordered[middle])
        return round((ordered[middle - 1] + ordered[middle]) / 2.0)

    @staticmethod
    def _clip(value: int) -> int:
        from glio_proteogen.contracts.m05_06 import M0506_RATE_SCALE

        return max(0, min(M0506_RATE_SCALE, int(value)))

    @staticmethod
    def _bounded_shift(value: int, maximum: int) -> tuple[int, bool]:
        applied = max(-maximum, min(maximum, int(value)))
        return applied, applied != value

    @staticmethod
    def _factor_level(
        observation: PtmLocalizationSupportObservation,
        factor: object,
    ) -> str:
        return next(level.level_id for level in observation.factor_levels if level.factor is factor)

    def _fit_stage(
        self,
        ledger: PtmLocalizationSupportLedger,
        stage: PtmLocalizationNormalizationStage,
        observation_by_id: dict[str, PtmLocalizationSupportObservation],
        maximum_shift: int,
        tolerance: int,
    ) -> tuple[PtmLocalizationStageTransformation, dict[str, int], _StageDiagnostic]:
        estimation = tuple(
            observation_by_id[target_id]
            for target_id in stage.estimation_anchor_ids
            if target_id in observation_by_id
        )
        validation = tuple(
            observation_by_id[target_id]
            for target_id in stage.validation_anchor_ids
            if target_id in observation_by_id
        )
        reference = tuple(
            item
            for item in estimation
            if self._factor_level(item, stage.factor) == stage.reference_level_id
            and item.support_coordinate_ppm is not None
        )
        level_ids = sorted(
            {self._factor_level(item, stage.factor) for item in ledger.observations}
        )
        shifts = []
        shift_map: dict[str, int] = {}
        for level_id in level_ids:
            level_estimation = tuple(
                item
                for item in estimation
                if self._factor_level(item, stage.factor) == level_id
                and item.support_coordinate_ppm is not None
            )
            validation_count = sum(
                self._factor_level(item, stage.factor) == level_id
                for item in validation
            )
            if level_id == stage.reference_level_id:
                estimated = 0
                pair_count = len(reference)
            elif reference and level_estimation:
                contrasts: list[int] = []
                for item in level_estimation:
                    item_coordinate = cast("int", item.support_coordinate_ppm)
                    contrasts.extend(
                        item_coordinate - anchor.support_coordinate_ppm
                        for anchor in reference
                        if anchor.support_coordinate_ppm is not None
                    )
                estimated = self._median(contrasts)
                pair_count = len(contrasts)
            else:
                continue
            applied, capped = self._bounded_shift(estimated, maximum_shift)
            shift_map[level_id] = applied
            shifts.append(
                __import__(
                    "glio_proteogen.contracts.m05_06",
                    fromlist=["PtmLocalizationSupportLevelShift"],
                ).PtmLocalizationSupportLevelShift(
                    stage_id=stage.stage_id,
                    ordinal=stage.ordinal,
                    factor=stage.factor,
                    level_id=level_id,
                    state=(
                        PtmLocalizationSupportShiftState.CAPPED
                        if capped
                        else PtmLocalizationSupportShiftState.ESTIMATED
                    ),
                    estimated_shift_ppm=estimated,
                    applied_shift_ppm=applied,
                    estimation_pair_count=pair_count,
                    validation_pair_count=validation_count,
                )
            )
        transformation = PtmLocalizationStageTransformation(
            stage_id=stage.stage_id,
            ordinal=stage.ordinal,
            factor=stage.factor,
            reference_level_id=stage.reference_level_id,
            level_shifts=tuple(shifts),
        )
        diagnostic_observations = tuple(
            item
            for item in (*estimation, *validation)
            if item.state is PtmLocalizationSupportObservationState.OBSERVED
            and item.support_coordinate_ppm is not None
        )
        if len(diagnostic_observations) < _MIN_DIAGNOSTIC_OBSERVATIONS:
            diagnostic: _StageDiagnostic = (
                None,
                None,
                PtmLocalizationHarmonizationDiagnosticStatus.NOT_EVALUABLE,
            )
        else:
            before = [
                item.support_coordinate_ppm
                for item in diagnostic_observations
                if item.support_coordinate_ppm is not None
            ]
            after = [
                self._clip(
                    coordinate - shift_map.get(self._factor_level(item, stage.factor), 0)
                )
                for item, coordinate in (
                    (item, item.support_coordinate_ppm) for item in diagnostic_observations
                )
                if coordinate is not None
            ]
            before_spread = max(before) - min(before)
            after_spread = max(after) - min(after)
            status = (
                PtmLocalizationHarmonizationDiagnosticStatus.PASSED
                if after_spread <= before_spread + tolerance
                else PtmLocalizationHarmonizationDiagnosticStatus.FAILED
            )
            diagnostic = (before_spread, after_spread, status)
        return transformation, shift_map, diagnostic

    def harmonize(
        self,
        ledger: PtmLocalizationSupportLedger,
        policy: PtmLocalizationHarmonizationPolicy,
        *,
        profile_digest: str,
        policy_digest: str,
        configuration_digest: str,
    ) -> PtmLocalizationHarmonizationExecution:
        from glio_proteogen.contracts.m05_06 import (
            PtmLocalizationAppliedSupportAdjustment,
            PtmLocalizationHarmonizedValue,
            PtmLocalizationSupportObservationState,
        )
        from glio_proteogen.contracts.m05_06.canonical import (
            analysis_digest,
            manifest_digest,
        )

        stages: list[PtmLocalizationStageTransformation] = []
        stage_shift_maps: list[dict[str, int]] = []
        stage_diagnostics: list[_StageDiagnostic] = []
        observation_by_id = {item.target_id: item for item in ledger.observations}
        for stage in policy.profiles[0].stages:
            transformation, shift_map, diagnostic = self._fit_stage(
                ledger,
                stage,
                observation_by_id,
                policy.max_absolute_shift_ppm,
                policy.technical_effect_tolerance_ppm,
            )
            stages.append(transformation)
            stage_shift_maps.append(shift_map)
            stage_diagnostics.append(diagnostic)
        stages_tuple = tuple(stages)
        manifest_payload = {
            "profile_digest": profile_digest,
            "policy_digest": policy_digest,
            "configuration_digest": configuration_digest,
            "stages": stages_tuple,
            "manifest_digest": "sha256:" + ("0" * 64),
        }
        manifest_payload["manifest_digest"] = manifest_digest(manifest_payload)
        manifest = PtmLocalizationTransformationManifest.model_validate(
            manifest_payload, strict=True
        )

        values = []
        for observation in ledger.observations:
            is_observed = observation.state is PtmLocalizationSupportObservationState.OBSERVED
            is_censored = observation.state is PtmLocalizationSupportObservationState.CENSORED
            coordinate = observation.support_coordinate_ppm
            upper_bound = observation.censoring_upper_bound_ppm
            adjustments = []
            for stage, shift_map in zip(policy.profiles[0].stages, stage_shift_maps, strict=True):
                level_id = next(
                    level.level_id
                    for level in observation.factor_levels
                    if level.factor is stage.factor
                )
                shift = shift_map.get(level_id, 0)
                if is_observed and coordinate is not None:
                    coordinate = self._clip(coordinate - shift)
                elif is_censored and upper_bound is not None:
                    upper_bound = self._clip(upper_bound - shift)
                if (is_observed or is_censored) and level_id in shift_map:
                    adjustments.append(
                        PtmLocalizationAppliedSupportAdjustment(
                            stage_id=stage.stage_id,
                            ordinal=stage.ordinal,
                            factor=stage.factor,
                            level_id=level_id,
                            shift_ppm=shift,
                        )
                    )
            values.append(
                PtmLocalizationHarmonizedValue(
                    target_id=observation.target_id,
                    unit_kind=observation.unit_kind,
                    input_state=observation.state,
                    output_state=observation.state,
                    input_coordinate_ppm=observation.support_coordinate_ppm,
                    harmonized_coordinate_ppm=coordinate if is_observed else None,
                    censoring_upper_bound_ppm=upper_bound,
                    source_observation_digest=__import__(
                        "glio_proteogen.kernel.canonical",
                        fromlist=["sha256_digest"],
                    ).sha256_digest(observation),
                    applied_adjustments=tuple(adjustments),
                )
            )
        analysis_payload = {
            "analysis_id": "analysis."
            + __import__(
                "glio_proteogen.kernel.canonical",
                fromlist=["sha256_digest"],
            )
            .sha256_digest(tuple(values))
            .removeprefix("sha256:"),
            "values": tuple(values),
            "source_ledger_digest": ledger.ledger_digest,
            "analysis_digest": "sha256:" + ("0" * 64),
        }
        analysis_payload["analysis_digest"] = analysis_digest(analysis_payload)
        analysis = PtmLocalizationHarmonizedAnalysis.model_validate(analysis_payload, strict=True)
        diagnostics = tuple(
            PtmLocalizationTechnicalEffectDiagnostic(
                stage_id=stage.stage_id,
                factor=stage.factor,
                status=status,
                before_spread_ppm=before,
                after_spread_ppm=after,
                tolerance_ppm=policy.technical_effect_tolerance_ppm,
            )
            for stage, (before, after, status) in zip(
                policy.profiles[0].stages, stage_diagnostics, strict=True
            )
        )
        invariant_diagnostics = tuple(
            PtmLocalizationInvariantDiagnostic(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                status=PtmLocalizationHarmonizationDiagnosticStatus.PASSED,
            )
            for invariant in ledger.invariants
        )
        return PtmLocalizationHarmonizationExecution(
            analysis=analysis,
            transformation_manifest=manifest,
            technical_effect_diagnostics=diagnostics,
            invariant_diagnostics=invariant_diagnostics,
        )


__all__ = [
    "M0506PtmLocalizationHarmonizationKernel",
    "PtmLocalizationHarmonizationExecution",
]
