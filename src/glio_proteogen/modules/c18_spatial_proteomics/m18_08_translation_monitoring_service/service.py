"""Strict service seam for M18-08 translation monitoring."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m18_08 import (
    BiomarkerPanelTranslationMonitoringResult,
    MonitorBiomarkerPanelTranslationHealthRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1808TranslationMonitoringEngine


class M1808Service:
    """Parse once, execute deterministically, and verify exact results."""

    def __init__(self, engine: M1808TranslationMonitoringEngine | None = None) -> None:
        self._engine = engine or M1808TranslationMonitoringEngine()

    def validate_request(self, request: object) -> MonitorBiomarkerPanelTranslationHealthRequest:
        return MonitorBiomarkerPanelTranslationHealthRequest.model_validate(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=4 * 1024 * 1024)
            request = strict_json_loads(canonical_json_bytes(parsed), max_bytes=4 * 1024 * 1024)
        elif isinstance(request, Mapping):
            request = dict(request)
        return self._engine.infer(request)

    def verify(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=8 * 1024 * 1024)
            result = strict_json_loads(canonical_json_bytes(parsed), max_bytes=8 * 1024 * 1024)
        elif isinstance(result, Mapping):
            result = dict(result)
        return self._engine.verify(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M18-08",
            "operation": "monitor_biomarker_panel_translation_health",
            "owner": "Scientific engineering",
            "safety_class": "S2",
            "gate": "G5",
            "parent": "biomarker panel",
            "provisional_abi": True,
            "prohibited_outputs": (
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M1808Service"]
