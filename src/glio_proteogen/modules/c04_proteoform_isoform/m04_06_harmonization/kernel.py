"""Exact fixed-point kernel for M04-06 proteoform harmonization."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizedAnalysis,
    ProteoformInvariantDiagnostic,
    ProteoformTechnicalEffectDiagnostic,
    ProteoformTransformationManifest,
    derive_harmonization,
)


@dataclass(frozen=True, slots=True)
class ProteoformHarmonizationExecution:
    """One immutable replay of the bounded fixed-point normalization kernel."""

    analysis: ProteoformHarmonizedAnalysis | None
    transformation_manifest: ProteoformTransformationManifest | None
    technical_effect_diagnostics: tuple[ProteoformTechnicalEffectDiagnostic, ...]
    invariant_diagnostics: tuple[ProteoformInvariantDiagnostic, ...]


class M0406ProteoformHarmonizationKernel:
    """Evaluate exact shifts and protected invariants without abundance arithmetic."""

    __slots__ = ()

    def harmonize(
        self,
        request: HarmonizeProteoformAnalysisRequest,
    ) -> ProteoformHarmonizationExecution:
        """Replay the contract-owned deterministic fixed-point transformation."""

        analysis, manifest, technical, invariants = derive_harmonization(request)
        return ProteoformHarmonizationExecution(
            analysis=analysis,
            transformation_manifest=manifest,
            technical_effect_diagnostics=technical,
            invariant_diagnostics=invariants,
        )


def execute_proteoform_harmonization(
    request: HarmonizeProteoformAnalysisRequest,
) -> ProteoformHarmonizationExecution:
    """Public stateless kernel operation for an already validated request."""

    return M0406ProteoformHarmonizationKernel().harmonize(request)


__all__ = [
    "M0406ProteoformHarmonizationKernel",
    "ProteoformHarmonizationExecution",
    "execute_proteoform_harmonization",
]
