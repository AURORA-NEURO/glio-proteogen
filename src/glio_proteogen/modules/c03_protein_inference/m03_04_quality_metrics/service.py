"""Stateless application boundary for M03-04 quality computation."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_RESULT_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceQualityResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.engine import (
    M0304ProteinInferenceQualityEngine,
    preflight_protein_inference_quality_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ComputeProteinInferenceQualityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceQualityResult)


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

    def verify(self, result: object) -> ProteinInferenceQualityResult:
        """Strictly replay-verify one stored result without recomputing inputs.

        M03-04 results are self-contained metadata receipts: the nested contract
        validator recomputes every metric, finding, digest, disposition,
        uncertainty, provenance, and evidence binding from the embedded request.
        Parse bytes through the duplicate-safe bounded JSON loader first, then
        canonicalize before Pydantic validation so mappings, models, and JSON
        documents share one replay path.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M0304_MAX_CANONICAL_RESULT_BYTES)
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


__all__ = ["M0304Service"]
