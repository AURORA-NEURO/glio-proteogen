"""Stateless application boundary for M03-05 artifact detection."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_05 import (
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection.engine import (
    M0305ProteinInferenceArtifactEngine,
    preflight_protein_inference_artifact_authorization,
    prepare_artifact_request_candidate,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)


class M0305Service:
    """Authorize and strictly validate one metadata-only artifact request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0305ProteinInferenceArtifactEngine | None = None) -> None:
        self._engine = engine or M0305ProteinInferenceArtifactEngine()

    @staticmethod
    def validate_request(request: object) -> DetectProteinInferenceArtifactsRequest:
        preflight_protein_inference_artifact_authorization(request)
        candidate = prepare_artifact_request_candidate(request)
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)

    def execute(self, request: object) -> ProteinInferenceArtifactDetectionResult:
        return self._engine.detect(request)


__all__ = ["M0305Service"]
