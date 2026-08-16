"""Strict parse-once service seam for M20-08."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m20_08 import (
    MonitorProteinSubtypeTranslationHealthRequest,
    ProteinSubtypeTranslationHealthResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2008TranslationMonitoringEngine


class M2008Service:
    """Parse once, execute deterministically, and verify exact results."""

    def __init__(self, engine: M2008TranslationMonitoringEngine | None = None) -> None:
        self._engine = engine or M2008TranslationMonitoringEngine()

    def validate_request(self, request: object) -> MonitorProteinSubtypeTranslationHealthRequest:
        return MonitorProteinSubtypeTranslationHealthRequest.model_validate(request, strict=True)

    def execute(self, request: object) -> ProteinSubtypeTranslationHealthResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=4 * 1024 * 1024)
            request = MonitorProteinSubtypeTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = MonitorProteinSubtypeTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.infer(request)

    def verify(self, result: object) -> ProteinSubtypeTranslationHealthResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=8 * 1024 * 1024)
            result = ProteinSubtypeTranslationHealthResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = ProteinSubtypeTranslationHealthResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        return self._engine.verify(result)

    def monitor(self, request: object) -> ProteinSubtypeTranslationHealthResult:
        return self.execute(request)

    def replay(self, result: object) -> ProteinSubtypeTranslationHealthResult:
        return self.verify(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M20-08",
            "operation": "monitor_protein_subtype_translation_health",
            "owner": "Bioinformatics",
            "safety_class": "S2",
            "gate": "G5",
            "parent": "protein subtype",
            "upstream_media_type": "application/vnd.glio-proteogen.m20-07+json",
            "provisional_abi": True,
            "prohibited_outputs": (
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2008Service"]
