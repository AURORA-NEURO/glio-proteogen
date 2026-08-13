"""Stateless application boundary for M03-04 quality computation."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04 import (
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.engine import (
    M0304ProteinInferenceQualityEngine,
    preflight_protein_inference_quality_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)


class M0304Service:
    """Authorize and strictly validate one metadata-only quality request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0304ProteinInferenceQualityEngine | None = None) -> None:
        self._engine = engine or M0304ProteinInferenceQualityEngine()

    @staticmethod
    def validate_request(request: object) -> ComputeProteinInferenceQualityRequest:
        preflight_protein_inference_quality_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinInferenceQualityResult:
        return self._engine.compute(request)


__all__ = ["M0304Service"]
