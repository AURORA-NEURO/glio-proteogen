"""Sealed M20-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M2003Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_03 import (
        FuseProteinSubtypeEvidenceRequest,
        ProteinSubtypeIntegratedEvidenceResult,
    )


@dataclass(frozen=True, slots=True)
class M2003PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-03"
    operation: str = "fuse_protein_subtype_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m20-03+json"
    parent_target: str = "protein subtype"
    owner: str = "Clinical science"
    safety_class: str = "S2"
    gate: str = "G2"
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


class M2003Plugin:
    """Expose only typed fusion and exact replay."""

    descriptor: Final = M2003PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2003Engine()

    def validate_request(self, candidate: object) -> FuseProteinSubtypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: FuseProteinSubtypeEvidenceRequest,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        return self._engine.fuse(request)

    def replay(
        self,
        result: ProteinSubtypeIntegratedEvidenceResult,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = ["M2003Plugin", "M2003PluginDescriptor"]
