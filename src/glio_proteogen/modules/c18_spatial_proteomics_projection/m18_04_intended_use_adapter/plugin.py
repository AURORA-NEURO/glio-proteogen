"""Sealed M18-04 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1804Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_04 import (
        AdaptBiomarkerPanelIntendedUseRequest,
        BiomarkerPanelIntendedUseAdapterResult,
    )


@dataclass(frozen=True, slots=True)
class M1804PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-04"
    operation: str = "adapt_biomarker_panel_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m18-04+json"
    parent_target: str = "biomarker panel"
    owner: str = "Quality engineering"
    safety_class: str = "S2"
    gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    intended_use_registration: bool = True
    explicit_abstention: bool = True


class M1804Plugin:
    descriptor: Final = M1804PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1804Engine()

    def validate_request(self, candidate: object) -> AdaptBiomarkerPanelIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: AdaptBiomarkerPanelIntendedUseRequest,
    ) -> BiomarkerPanelIntendedUseAdapterResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: BiomarkerPanelIntendedUseAdapterResult,
    ) -> BiomarkerPanelIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1804Plugin", "M1804PluginDescriptor"]
