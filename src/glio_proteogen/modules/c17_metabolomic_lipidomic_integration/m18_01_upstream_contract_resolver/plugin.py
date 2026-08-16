"""Sealed M18-01 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1801Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_01 import (
        BiomarkerPanelUpstreamResolutionResult,
        ResolveBiomarkerPanelUpstreamContractsRequest,
    )


@dataclass(frozen=True, slots=True)
class M1801PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-01"
    operation: str = "resolve_biomarker_panel_upstream_contracts"
    output_media_type: str = "application/vnd.glio-proteogen.m18-01+json"
    parent_target: str = "biomarker panel"
    owner: str = "Computational biology"
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


class M1801Plugin:
    """Expose only typed request resolution and exact replay."""

    descriptor: Final = M1801PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1801Engine()

    def validate_request(self, candidate: object) -> ResolveBiomarkerPanelUpstreamContractsRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: ResolveBiomarkerPanelUpstreamContractsRequest,
    ) -> BiomarkerPanelUpstreamResolutionResult:
        return self._engine.resolve(request)

    def replay(
        self,
        result: BiomarkerPanelUpstreamResolutionResult,
    ) -> BiomarkerPanelUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = ["M1801Plugin", "M1801PluginDescriptor"]
