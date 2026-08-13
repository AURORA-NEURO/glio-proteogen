"""Exact fixed-point kernel for M03-06 protein-inference harmonization."""

from __future__ import annotations

from dataclasses import dataclass

from glio_proteogen.contracts.m03_06 import (
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizedAnalysis,
    ProteinInferenceInvariantDiagnostic,
    ProteinInferenceTechnicalEffectDiagnostic,
    ProteinInferenceTransformationManifest,
    derive_harmonization,
)


@dataclass(frozen=True, slots=True)
class ProteinInferenceHarmonizationExecution:
    """One immutable replay of the bounded fixed-point normalization kernel."""

    analysis: ProteinInferenceHarmonizedAnalysis | None
    transformation_manifest: ProteinInferenceTransformationManifest | None
    technical_effect_diagnostics: tuple[ProteinInferenceTechnicalEffectDiagnostic, ...]
    invariant_diagnostics: tuple[ProteinInferenceInvariantDiagnostic, ...]


class M0306ProteinInferenceHarmonizationKernel:
    """Evaluate exact shifts and protected invariants without abundance arithmetic."""

    __slots__ = ()

    def harmonize(
        self,
        request: HarmonizeProteinInferenceSupportRequest,
    ) -> ProteinInferenceHarmonizationExecution:
        """Replay the contract-owned deterministic fixed-point transformation."""

        analysis, manifest, technical, invariants = derive_harmonization(request)
        return ProteinInferenceHarmonizationExecution(
            analysis=analysis,
            transformation_manifest=manifest,
            technical_effect_diagnostics=technical,
            invariant_diagnostics=invariants,
        )


def execute_protein_inference_harmonization(
    request: HarmonizeProteinInferenceSupportRequest,
) -> ProteinInferenceHarmonizationExecution:
    """Public stateless kernel operation for an already validated request."""

    return M0306ProteinInferenceHarmonizationKernel().harmonize(request)


__all__ = [
    "M0306ProteinInferenceHarmonizationKernel",
    "ProteinInferenceHarmonizationExecution",
    "execute_protein_inference_harmonization",
]
