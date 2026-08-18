"""Stateless application boundary for M05-05 artifact detection."""

from glio_proteogen.contracts.m05_05 import (
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDetectionResult,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection.engine import (
    M0505PtmLocalizationArtifactEngine,
    _prepare_artifact_request_candidate,
    _validate_prepared_request,
)


class M0505Service:
    """Authorize and strictly validate one aggregate-only artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0505PtmLocalizationArtifactEngine | None = None) -> None:
        self._engine = engine or M0505PtmLocalizationArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectPtmLocalizationArtifactsRequest:
        candidate = _prepare_artifact_request_candidate(request)
        return _validate_prepared_request(candidate)

    def _execute_validated(
        self,
        request: DetectPtmLocalizationArtifactsRequest,
    ) -> PtmLocalizationArtifactDetectionResult:
        return self._engine._detect_validated(request)

    def execute(self, request: object) -> PtmLocalizationArtifactDetectionResult:
        return self._engine.detect(request)


__all__ = ["M0505Service"]
