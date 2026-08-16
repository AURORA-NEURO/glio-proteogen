"""Service seam for the provisional M13-04 runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_04 import InferProteotypeMechanismRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from glio_proteogen.contracts.m13_04 import ProteotypeMechanismInferenceResult

from .engine import M1304MechanismEngine

_REQUEST_ADAPTER = TypeAdapter(InferProteotypeMechanismRequest)


class M1304Service:
    """Keep adapter execution and replay verification on one engine seam."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M1304MechanismEngine | None = None) -> None:
        self._engine = engine or M1304MechanismEngine()

    def execute(
        self, request: InferProteotypeMechanismRequest
    ) -> ProteotypeMechanismInferenceResult:
        return self._engine.infer(request)

    def validate_request(self, request: object) -> InferProteotypeMechanismRequest:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)

    def _execute_validated(
        self, request: InferProteotypeMechanismRequest
    ) -> ProteotypeMechanismInferenceResult:
        return self._engine.infer(request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeMechanismInferenceResult:
        return self._engine.verify(result, replay=replay)


__all__ = ["M1304Service"]
