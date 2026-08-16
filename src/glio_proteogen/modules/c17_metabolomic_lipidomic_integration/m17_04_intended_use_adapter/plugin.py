"""Sealed M17-04 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1704Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_04 import (
        AdaptVariantPeptideIntendedUseRequest,
        VariantPeptideIntendedUseAdapterResult,
    )


@dataclass(frozen=True, slots=True)
class M1704PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M17-04"
    operation: str = "adapt_variant_peptide_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m17-04+json"
    parent_target: str = "variant peptide"
    owner: str = "ML engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_policy: bool = True
    explicit_abstention: bool = True


class M1704Plugin:
    """Expose only bounded policy adaptation and exact replay."""

    descriptor: Final = M1704PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1704Engine()

    def validate_request(self, candidate: object) -> AdaptVariantPeptideIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: AdaptVariantPeptideIntendedUseRequest,
    ) -> VariantPeptideIntendedUseAdapterResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: VariantPeptideIntendedUseAdapterResult,
    ) -> VariantPeptideIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1704Plugin", "M1704PluginDescriptor"]
