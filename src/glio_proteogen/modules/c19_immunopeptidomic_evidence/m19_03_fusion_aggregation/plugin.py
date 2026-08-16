"""Sealed M19-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1903Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_03 import (
        FuseProteotypeEvidenceRequest,
        ProteotypeIntegratedEvidenceResult,
    )


@dataclass(frozen=True, slots=True)
class M1903PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-03"
    operation: str = "fuse_proteotype_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m19-03+json"
    parent_target: str = "proteotype"
    owner: str = "Quality engineering"
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


class M1903Plugin:
    """Expose only component-specific fusion and exact replay."""

    descriptor: Final = M1903PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1903Engine()

    def validate_request(self, candidate: object) -> FuseProteotypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: FuseProteotypeEvidenceRequest,
    ) -> ProteotypeIntegratedEvidenceResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: ProteotypeIntegratedEvidenceResult,
    ) -> ProteotypeIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M1903Plugin", "M1903PluginDescriptor"]
