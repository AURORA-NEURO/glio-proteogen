"""Sealed M17-01 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1701Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_01 import (
        ResolveVariantPeptideUpstreamContractsRequest,
        VariantPeptideUpstreamResolutionResult,
    )


@dataclass(frozen=True, slots=True)
class M1701PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M17-01"
    operation: str = "resolve_variant_peptide_upstream_contracts"
    output_media_type: str = "application/vnd.glio-proteogen.m17-01+json"
    parent_target: str = "variant peptide"
    owner: str = "Scientific engineering"
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


class M1701Plugin:
    """Expose only typed request resolution and exact replay."""

    descriptor: Final = M1701PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1701Engine()

    def validate_request(self, candidate: object) -> ResolveVariantPeptideUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: ResolveVariantPeptideUpstreamContractsRequest,
    ) -> VariantPeptideUpstreamResolutionResult:
        return self._engine.resolve(request)

    def replay(
        self,
        result: VariantPeptideUpstreamResolutionResult,
    ) -> VariantPeptideUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M1701Plugin", "M1701PluginDescriptor"]
