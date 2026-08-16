"""Strict service seam for M19-08 monitoring and rollback."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m19_08 import (
    MonitorProteotypeTranslationHealthRequest,
    ProteotypeTranslationMonitoringResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1908TranslationMonitoringEngine


class M1908Service:
    """Parse once, execute deterministically, and verify exact results."""

    def __init__(self, engine: M1908TranslationMonitoringEngine | None = None) -> None:
        self._engine = engine or M1908TranslationMonitoringEngine()

    def validate_request(self, request: object) -> MonitorProteotypeTranslationHealthRequest:
        return self._engine.validate_request(request)

    def execute(self, request: object) -> ProteotypeTranslationMonitoringResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=4 * 1024 * 1024)
            request = MonitorProteotypeTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = MonitorProteotypeTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.infer(request)

    def verify(self, result: object) -> ProteotypeTranslationMonitoringResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=8 * 1024 * 1024)
            result = ProteotypeTranslationMonitoringResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = ProteotypeTranslationMonitoringResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        return self._engine.verify(result)

    def monitor(self, request: object) -> ProteotypeTranslationMonitoringResult:
        return self.execute(request)

    def replay(self, result: object) -> ProteotypeTranslationMonitoringResult:
        return self.verify(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M19-08",
            "operation": "monitor_proteotype_translation_health",
            "owner": "Computational biology",
            "safety_class": "S2",
            "gate": "G5",
            "parent": "proteotype",
            "provisional_abi": True,
            "external_content_traversal": False,
            "generic_all_omics_fusion": False,
            "kinase_activity": False,
            "treatment_recommendation": False,
            "identity_inference": False,
            "consent_inference": False,
            "unsupported_to_negative": False,
            "suspension_and_rollback": True,
        }


__all__ = ["M1908Service"]
