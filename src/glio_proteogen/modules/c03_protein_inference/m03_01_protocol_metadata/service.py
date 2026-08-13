"""Stateless application boundary for M03-01 protocol conformance."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_01.v1 import (
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata.engine import (
    M0301ProteinInferenceProtocolEngine,
    preflight_protein_inference_protocol_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinInferenceProtocolRequest)


class M0301Service:
    """Authorize and strictly validate before evaluating the reviewed protocol."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0301ProteinInferenceProtocolEngine | None = None) -> None:
        self._engine = engine or M0301ProteinInferenceProtocolEngine()

    @staticmethod
    def validate_request(request: object) -> EvaluateProteinInferenceProtocolRequest:
        preflight_protein_inference_protocol_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinInferenceProtocolConformanceResult:
        return self._engine.evaluate(request)


__all__ = ["M0301Service"]
