"""Thin stateless service for M01-05."""

from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_05 import ArtifactDetectionResult, DetectArtifactsRequest
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection.engine import (
    M0105DetectionEngine,
)

_REQUEST_ADAPTER: Final[TypeAdapter[DetectArtifactsRequest]] = TypeAdapter(
    DetectArtifactsRequest
)


class M0105Service:
    """Revalidate and delegate one artifact-detection request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0105DetectionEngine | None = None) -> None:
        self._engine = engine or M0105DetectionEngine()

    @staticmethod
    def validate_request(request: object) -> DetectArtifactsRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ArtifactDetectionResult:
        return self._engine.detect(self.validate_request(request))


__all__ = ["M0105Service"]
