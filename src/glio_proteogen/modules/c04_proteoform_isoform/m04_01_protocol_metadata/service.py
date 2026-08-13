"""Stateless application boundary for M04-01 protocol conformance."""

from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_01 import (
    EvaluateProteoformProtocolRequest,
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata.engine import (
    M0401ProteoformProtocolEngine,
    _plain_value,
    preflight_proteoform_protocol_authorization,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteoformProtocolRequest)


class M0401Service:
    """Authorize and strictly validate before evaluating protocol conformance."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M0401ProteoformProtocolEngine | None = None) -> None:
        self._engine = engine or M0401ProteoformProtocolEngine()

    @staticmethod
    def validate_request(request: object) -> EvaluateProteoformProtocolRequest:
        preflight_proteoform_protocol_authorization(request)
        return _REQUEST_ADAPTER.validate_python(_plain_value(request), strict=True)

    def execute(self, request: object) -> ProteoformProtocolConformanceResult:
        return self._engine.evaluate(request)


__all__ = ["M0401Service"]
