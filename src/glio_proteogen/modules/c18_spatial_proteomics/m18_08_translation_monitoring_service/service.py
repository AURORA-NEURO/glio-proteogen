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
        return MonitorBiomarkerPanelTranslationHealthRequest.model_validate(request, strict=True)

    def execute(self, request: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=M1808_MAX_CANONICAL_REQUEST_BYTES)
            request = MonitorBiomarkerPanelTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = MonitorBiomarkerPanelTranslationHealthRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.infer(request)

    def execute_validated(
        self, request: MonitorBiomarkerPanelTranslationHealthRequest
    ) -> BiomarkerPanelTranslationMonitoringResult:
        """Execute one already-validated request through the public service seam."""

        return self._engine.infer(request)

    def verify(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=M1808_MAX_CANONICAL_RESULT_BYTES)
            result = BiomarkerPanelTranslationMonitoringResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = BiomarkerPanelTranslationMonitoringResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
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
            "upstream_input_media_type": "application/vnd.glio-proteogen.m18-07+json",
            "output_media_type": "application/vnd.glio-proteogen.m18-08+json",
            "provisional_abi": True,
            "external_content_traversal": False,
            "raw_payload": False,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M1808Service"]
