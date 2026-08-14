"""Stateless application boundary for M04-05 artifact detection."""

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_05 import (
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection.engine import (
    M0405ProteoformArtifactEngine,
    prepare_artifact_request_candidate,
)


class M0405Service:
    """Authorize and strictly validate one aggregate-only artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0405ProteoformArtifactEngine | None = None) -> None:
        self._engine = engine or M0405ProteoformArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectProteoformArtifactsRequest:
        candidate = prepare_artifact_request_candidate(request)
        return TypeAdapter(DetectProteoformArtifactsRequest).validate_python(candidate, strict=True)

    def execute(self, request: object) -> ProteoformArtifactDetectionResult:
        return self._engine.detect(request)


__all__ = ["M0405Service"]
