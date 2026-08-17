"""Stateless application boundary for M04-05 artifact detection."""

from glio_proteogen.contracts.m04_05 import (
    DetectProteoformArtifactsRequest,
    ProteoformArtifactDetectionResult,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection.engine import (
    M0405ProteoformArtifactEngine,
    _prepare_artifact_request_candidate,
    _validate_prepared_request,
)


class M0405Service:
    """Authorize and strictly validate one aggregate-only artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0405ProteoformArtifactEngine | None = None) -> None:
        self._engine = engine or M0405ProteoformArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectProteoformArtifactsRequest:
        candidate = _prepare_artifact_request_candidate(request)
        return _validate_prepared_request(candidate)

    def _execute_validated(
        self,
        request: DetectProteoformArtifactsRequest,
    ) -> ProteoformArtifactDetectionResult:
        return self._engine._detect_validated(request)

    def execute(self, request: object) -> ProteoformArtifactDetectionResult:
        return self._engine.detect(request)


__all__ = ["M0405Service"]
