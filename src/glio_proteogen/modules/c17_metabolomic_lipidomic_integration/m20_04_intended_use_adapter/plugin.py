"""Sealed M20-04 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M2004Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_04 import (
        AdaptProteinSubtypeIntendedUseRequest,
        ProteinSubtypeIntendedUseAdapterResult,
    )


@dataclass(frozen=True, slots=True)
class M2004PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-04"
    operation: str = "adapt_protein_subtype_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m20-04+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-03+json"
    parent_target: str = "protein subtype"
    owner: str = "Data engineering"
    safety_class: str = "S2"
    gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    explicit_abstention: bool = True
    claim_ceiling_required: bool = True
    display_semantics_required: bool = True
    evidence_tier_required: bool = True


class M2004Plugin:
    """Expose only typed adaptation and exact replay."""

    descriptor: Final = M2004PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2004Engine()

    def validate_request(self, candidate: object) -> AdaptProteinSubtypeIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: AdaptProteinSubtypeIntendedUseRequest,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: ProteinSubtypeIntendedUseAdapterResult,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M2004Plugin", "M2004PluginDescriptor"]
