"""Strict service seam for M18-08 translation monitoring."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m18_08 import (
    M1808_MAX_CANONICAL_REQUEST_BYTES,
    M1808_MAX_CANONICAL_RESULT_BYTES,
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
        if isinstance(request, Mapping):
            serialized = _bounded_mapping_bytes(request, M1808_MAX_CANONICAL_REQUEST_BYTES)
            return MonitorBiomarkerPanelTranslationHealthRequest.model_validate_json(
                serialized, strict=True
            )
        return MonitorBiomarkerPanelTranslationHealthRequest.model_validate(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=4 * 1024 * 1024)
            request = MonitorBiomarkerPanelTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            serialized = _bounded_mapping_bytes(request, M1808_MAX_CANONICAL_REQUEST_BYTES)
            request = MonitorBiomarkerPanelTranslationHealthRequest.model_validate_json(
                serialized, strict=True
            )
        return self._engine.infer(request)

    def verify(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=8 * 1024 * 1024)
            result = BiomarkerPanelTranslationMonitoringResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            serialized = _bounded_mapping_bytes(result, M1808_MAX_CANONICAL_RESULT_BYTES)
            result = BiomarkerPanelTranslationMonitoringResult.model_validate_json(
                serialized, strict=True
            )
        return self._engine.verify(result)

    def monitor(self, request: object) -> BiomarkerPanelTranslationMonitoringResult:
        """Named service operation for translation-health monitoring."""

        return self.execute(request)

    def replay(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        """Named service operation for exact replay verification."""

        return self.verify(result)

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


def _bounded_mapping_bytes(value: Mapping[object, object], maximum: int) -> bytes:
    serialized = canonical_json_bytes(dict(value))
    if len(serialized) > maximum:
        raise ValueError("M18-08 mapping payload exceeds its canonical byte limit")  # noqa: TRY003
    return serialized


__all__ = ["M1808Service"]
