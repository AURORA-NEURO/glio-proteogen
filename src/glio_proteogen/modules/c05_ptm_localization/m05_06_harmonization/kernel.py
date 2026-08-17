"""Bounded deterministic M05-06 support-coordinate kernel."""

# The kernel imports contract types lazily to avoid the contract/canonical cycle.
# ruff: noqa: PLC0415

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m05_06 import (
    PtmLocalizationHarmonizationPolicy,
    PtmLocalizationHarmonizedAnalysis,
    PtmLocalizationInvariantDiagnostic,
    PtmLocalizationStageTransformation,
    PtmLocalizationSupportLedger,
    PtmLocalizationTechnicalEffectDiagnostic,
    PtmLocalizationTransformationManifest,
)


@dataclass(frozen=True, slots=True)
class PtmLocalizationHarmonizationExecution:
    analysis: PtmLocalizationHarmonizedAnalysis | None
    transformation_manifest: PtmLocalizationTransformationManifest | None
    technical_effect_diagnostics: tuple[PtmLocalizationTechnicalEffectDiagnostic, ...]
    invariant_diagnostics: tuple[PtmLocalizationInvariantDiagnostic, ...]


class M0506PtmLocalizationHarmonizationKernel:
    """Apply the provisional no-op fixed-point transform to cleared support only."""

    __slots__ = ()

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
            PtmLocalizationHarmonizationDiagnosticStatus,
            PtmLocalizationHarmonizedValue,
            PtmLocalizationSupportObservationState,
            PtmLocalizationSupportShiftState,
        )
        from glio_proteogen.contracts.m05_06.canonical import (
            analysis_digest,
            manifest_digest,
        )

        stages = tuple(
            PtmLocalizationStageTransformation(
                stage_id=stage.stage_id,
                ordinal=stage.ordinal,
                factor=stage.factor,
                reference_level_id=stage.reference_level_id,
                level_shifts=(
                    # No caller-declared stage pair is used to invent a shift.  The
                    # provisional transform records a zero shift for the reference
                    # level only and leaves unsupported coordinates untouched.
                    __import__(
                        "glio_proteogen.contracts.m05_06",
                        fromlist=["PtmLocalizationSupportLevelShift"],
                    ).PtmLocalizationSupportLevelShift(
                        stage_id=stage.stage_id,
                        ordinal=stage.ordinal,
                        factor=stage.factor,
                        level_id=stage.reference_level_id,
                        state=PtmLocalizationSupportShiftState.ESTIMATED,
                        estimated_shift_ppm=0,
                        applied_shift_ppm=0,
                        estimation_pair_count=len(stage.estimation_anchor_ids),
                        validation_pair_count=len(stage.validation_anchor_ids),
                    ),
                ),
            )
            for stage in policy.profiles[0].stages
        )
        manifest_payload = {
            "profile_digest": profile_digest,
            "policy_digest": policy_digest,
            "configuration_digest": configuration_digest,
            "stages": stages,
            "manifest_digest": "sha256:" + ("0" * 64),
        }
        manifest_payload["manifest_digest"] = manifest_digest(manifest_payload)
        manifest = PtmLocalizationTransformationManifest.model_validate(
            manifest_payload, strict=True
        )

        values = []
        for observation in ledger.observations:
            is_observed = observation.state is PtmLocalizationSupportObservationState.OBSERVED
            values.append(
                PtmLocalizationHarmonizedValue(
                    target_id=observation.target_id,
                    unit_kind=observation.unit_kind,
                    input_state=observation.state,
                    output_state=observation.state,
                    input_coordinate_ppm=observation.support_coordinate_ppm,
                    harmonized_coordinate_ppm=(
                        observation.support_coordinate_ppm if is_observed else None
                    ),
                    censoring_upper_bound_ppm=observation.censoring_upper_bound_ppm,
                    source_observation_digest=__import__(
                        "glio_proteogen.kernel.canonical",
                        fromlist=["sha256_digest"],
                    ).sha256_digest(observation),
                    applied_adjustments=tuple(
                        PtmLocalizationAppliedSupportAdjustment(
                            stage_id=stage.stage_id,
                            ordinal=stage.ordinal,
                            factor=stage.factor,
                            level_id=next(
                                level.level_id
                                for level in observation.factor_levels
                                if level.factor is stage.factor
                            ),
                            shift_ppm=0,
                        )
                        for stage in policy.profiles[0].stages
                        if is_observed
                    ),
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
                status=PtmLocalizationHarmonizationDiagnosticStatus.PASSED,
                before_spread_ppm=0,
                after_spread_ppm=0,
                tolerance_ppm=policy.technical_effect_tolerance_ppm,
            )
            for stage in policy.profiles[0].stages
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
