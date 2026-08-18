"""Stateless application boundary for M03-05 artifact detection."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_05 import (
    M0305_MAX_CANONICAL_RESULT_BYTES,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_05_artifact_detection.engine import (
    M0305ProteinInferenceArtifactEngine,
    preflight_protein_inference_artifact_authorization,
    prepare_artifact_request_candidate,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DetectProteinInferenceArtifactsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceArtifactDetectionResult)


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

    def verify(self, result: object) -> ProteinInferenceArtifactDetectionResult:
        """Replay-verify one stored M03-05 result through its closed envelope.

        The result contract recomputes the signal matrix, categorical reduction,
        contamination flags, exclusion mask, findings, support, provenance,
        evidence index, and digest from the embedded request.  This method is a
        bounded, duplicate-safe ingress for that verifier so API, CLI, and
        library callers share the same replay path.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M0305_MAX_CANONICAL_RESULT_BYTES)
            return _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        if isinstance(result, Mapping):
            return _RESULT_ADAPTER.validate_json(
                canonical_json_bytes(dict(result)),
                strict=True,
            )
        return _RESULT_ADAPTER.validate_json(
            canonical_json_bytes(result),
            strict=True,
        )


__all__ = ["M0305Service"]
