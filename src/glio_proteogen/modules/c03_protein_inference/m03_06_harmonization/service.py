"""Stateless application boundary for M03-06 support harmonization."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_RESULT_BYTES,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceHarmonizationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization.engine import (
    M0306ProteinInferenceHarmonizationEngine,
    preflight_protein_inference_harmonization_authorization,
    prepare_harmonization_request_candidate,
)

_REQUEST_ADAPTER: Final = TypeAdapter(HarmonizeProteinInferenceSupportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceHarmonizationResult)


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

    def verify(self, result: object) -> ProteinInferenceHarmonizationResult:
        """Strictly replay-verify one stored harmonization result.

        The result contract replays its embedded request, transformations,
        findings, evidence, uncertainty, and canonical digest.  This boundary
        accepts only bounded duplicate-safe JSON or canonical model data; it
        never reopens upstream payloads or consults mutable state.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M0306_MAX_CANONICAL_RESULT_BYTES)
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


__all__ = ["M0306Service"]
