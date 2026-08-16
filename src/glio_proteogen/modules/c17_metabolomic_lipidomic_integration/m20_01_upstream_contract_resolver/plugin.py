"""Sealed M20-01 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M2001Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_01 import (
        ProteinSubtypeUpstreamResolutionResult,
        ResolveProteinSubtypeUpstreamContractsRequest,
    )


@dataclass(frozen=True, slots=True)
class M2001PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-01"
    operation: str = "resolve_protein_subtype_upstream_contracts"
    output_media_type: str = "application/vnd.glio-proteogen.m20-01+json"
    parent_target: str = "protein subtype"
    owner: str = "ML engineering"
    safety_class: str = "S2"
    gate: str = "G0"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_discovery: bool = True
    typed_rejections: bool = True
    explicit_abstention: bool = True


class M2001Plugin:
    """Expose only typed request resolution and exact replay."""

    descriptor: Final = M2001PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2001Engine()

    def validate_request(self, candidate: object) -> ResolveProteinSubtypeUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: ResolveProteinSubtypeUpstreamContractsRequest,
    ) -> ProteinSubtypeUpstreamResolutionResult:
        return self._engine.resolve(request)

    def replay(
        self,
        result: ProteinSubtypeUpstreamResolutionResult,
    ) -> ProteinSubtypeUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M2001Plugin", "M2001PluginDescriptor"]
