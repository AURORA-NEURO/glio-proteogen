"""Sealed M17-08 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .engine import M1708Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m17_08 import (
        MonitorVariantPeptideTranslationHealthRequest,
        VariantPeptideTranslationMonitoringResult,
    )


@dataclass(frozen=True, slots=True)
class M1708PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M17-08"
    operation: str = "monitor_variant_peptide_translation_health"
    output_media_type: str = "application/vnd.glio-proteogen.m17-08+json"
    parent_target: str = "variant peptide"
    owner: str = "Platform engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G5"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_health_state: bool = True
    explicit_abstention: bool = True


class M1708Plugin:
    """Expose only bounded health monitoring and exact replay."""

    descriptor: Final = M1708PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1708Engine()

    def validate_request(self, candidate: object) -> MonitorVariantPeptideTranslationHealthRequest:
        return self._engine.validate_request(candidate)

    def run(
        self,
        request: MonitorVariantPeptideTranslationHealthRequest,
    ) -> VariantPeptideTranslationMonitoringResult:
        return self._engine.adapt(request)

    def replay(
        self,
        result: VariantPeptideTranslationMonitoringResult,
    ) -> VariantPeptideTranslationMonitoringResult:
        return self._engine.replay(result)


__all__ = ["M1708Plugin", "M1708PluginDescriptor"]
