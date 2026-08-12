"""Thin stateless service for M02-05 identification-artifact detection."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_05 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection.engine import (
    M0205IdentificationArtifactEngine,
    preflight_identification_artifact_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DetectIdentificationArtifactsRequest)


class M0205Service:
    """Validate and execute one identification-artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0205IdentificationArtifactEngine | None = None) -> None:
        self._engine = engine or M0205IdentificationArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectIdentificationArtifactsRequest:
        preflight_identification_artifact_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> IdentificationArtifactDetectionResult:
        return self._engine.detect(request)


__all__ = ["M0205Service"]
