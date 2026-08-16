"""M11-02 application service boundary."""

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_02 import (
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1102ContextEngine, _prepare, preflight_context_authorization

_REQUEST_ADAPTER = TypeAdapter(StratifyVariantPeptideContextRequest)


class M1102Service:
    """Authorize, validate, stratify, and verify one context request."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1102ContextEngine | None = None) -> None:
        self._engine = engine or M1102ContextEngine()

    @staticmethod
    def validate_request(request: object) -> StratifyVariantPeptideContextRequest:
        return StratifyVariantPeptideContextRequest.model_validate(_prepare(request), strict=True)

    @staticmethod
    def validate_json(payload: bytes | bytearray | str) -> StratifyVariantPeptideContextRequest:
        """Strictly parse one JSON document after duplicate-key and authorization checks."""

        parsed = strict_json_loads(payload)
        preflight_context_authorization(parsed)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)

    def _execute_validated(
        self,
        request: StratifyVariantPeptideContextRequest,
    ) -> VariantPeptideContextStratificationResult:
        return self._engine.stratify(request)

    def execute(self, request: object) -> VariantPeptideContextStratificationResult:
        return self._engine.stratify(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideContextStratificationResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1102Service"]
