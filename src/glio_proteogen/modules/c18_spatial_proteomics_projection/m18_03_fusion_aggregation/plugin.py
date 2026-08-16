"""Sealed M18-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1803Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_03 import (
        BiomarkerPanelIntegratedEvidenceResult,
        FuseBiomarkerPanelEvidenceRequest,
    )


@dataclass(frozen=True, slots=True)
class M1803PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-03"
    operation: str = "fuse_biomarker_panel_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m18-03+json"
    parent_target: str = "biomarker panel"
    owner: str = "ML engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G2"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    source_attribution: bool = True
    disagreement_preservation: bool = True
    explicit_abstention: bool = True


class M1803Plugin:
    """Expose only component-specific fusion and exact replay."""

    descriptor: Final = M1803PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1803Engine()

    def validate_request(self, candidate: object) -> FuseBiomarkerPanelEvidenceRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: FuseBiomarkerPanelEvidenceRequest,
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: BiomarkerPanelIntegratedEvidenceResult,
    ) -> BiomarkerPanelIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M1803Plugin", "M1803PluginDescriptor"]
