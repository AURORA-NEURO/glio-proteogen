"""Sealed strict M20-02 plugin descriptor and parse-once boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M2002Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_02 import (
        AlignProteinSubtypeSourcesRequest,
        ProteinSubtypeAlignmentResult,
    )


@dataclass(frozen=True, slots=True)
class M2002PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-02"
    operation: str = "align_protein_subtype_sources"
    output_media_type: str = "application/vnd.glio-proteogen.m20-02+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-01+json"
    parent_target: str = "protein subtype"
    owner: str = "Quality engineering"
    safety_class: str = "S2"
    gate: str = "G1"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_discovery: bool = True
    explicit_abstention: bool = True


class M2002Plugin:
    """Expose strict request validation, reconciliation, and exact replay."""

    descriptor: Final = M2002PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2002Engine()

    def validate_request(self, candidate: object) -> AlignProteinSubtypeSourcesRequest:
        return self._engine.validate_request(candidate)

    def run(self, request: AlignProteinSubtypeSourcesRequest) -> ProteinSubtypeAlignmentResult:
        return self._engine.resolve(request)

    def verify(self, result: ProteinSubtypeAlignmentResult) -> ProteinSubtypeAlignmentResult:
        return self._engine.replay(result)


__all__ = ["M2002Plugin", "M2002PluginDescriptor"]
