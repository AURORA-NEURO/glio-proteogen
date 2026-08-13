"""Stateless application boundary for M03-06 support harmonization."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_06 import (
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.engine import (
    M0306ProteinInferenceHarmonizationEngine,
    preflight_protein_inference_harmonization_authorization,
    prepare_harmonization_request_candidate,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)


class M0306Service:
    """Authorize and strictly validate one metadata-only harmonization request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0306ProteinInferenceHarmonizationEngine | None = None,
    ) -> None:
        self._engine = engine or M0306ProteinInferenceHarmonizationEngine()

    @staticmethod
    def validate_request(request: object) -> HarmonizeProteinInferenceSupportRequest:
        preflight_protein_inference_harmonization_authorization(request)
        candidate = prepare_harmonization_request_candidate(request)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def execute(self, request: object) -> ProteinInferenceHarmonizationResult:
        return self._engine.harmonize(request)


__all__ = ["M0306Service"]
