"""Stateless application boundary for M03-07 protein-inference support routing."""

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_07 import (
    M0307_MAX_CANONICAL_RESULT_BYTES,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router.engine import (
    M0307ProteinInferenceSupportRouterEngine,
    preflight_protein_inference_support_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(RouteProteinInferenceSupportRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinInferenceSupportRouteResult)


class _ResultSizeError(ValueError):
    """Raised when canonical result content exceeds the frozen M03-07 ceiling."""

    def __init__(self) -> None:
        super().__init__("M03-07 result exceeds its canonical byte limit")


def _bounded_result_bytes(value: object) -> bytes:
    """Canonicalize every result ingress shape under the same byte ceiling."""

    payload = canonical_json_bytes(value)
    if len(payload) > M0307_MAX_CANONICAL_RESULT_BYTES:
        raise _ResultSizeError
    return payload


class M0307Service:
    """Authorize, strictly validate, and route one immutable request."""

    __slots__ = ("_engine",)

    def __init__(
        self,
        engine: M0307ProteinInferenceSupportRouterEngine | None = None,
    ) -> None:
        self._engine = engine or M0307ProteinInferenceSupportRouterEngine()

    @staticmethod
    def validate_request(request: object) -> RouteProteinInferenceSupportRequest:
        preflight_protein_inference_support_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def execute(self, request: object) -> ProteinInferenceSupportRouteResult:
        return self._engine.route(request)

    def verify(self, result: object) -> ProteinInferenceSupportRouteResult:
        """Strictly replay-verify one stored support-routing result.

        M03-07 results carry the complete request, compact prerequisites,
        envelope assessments, abstention reasons, evidence, provenance, and
        canonical digest.  This bounded boundary validates that closed result
        without reopening upstream payloads or consulting mutable state.
        """

        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M0307_MAX_CANONICAL_RESULT_BYTES)
            return _RESULT_ADAPTER.validate_json(_bounded_result_bytes(decoded), strict=True)
        if isinstance(result, Mapping):
            return _RESULT_ADAPTER.validate_json(
                _bounded_result_bytes(dict(result)),
                strict=True,
            )
        return _RESULT_ADAPTER.validate_json(
            _bounded_result_bytes(result),
            strict=True,
        )


__all__ = ["M0307Service"]
