"""Strict parse-once plugin adapter for M27-03."""

# Boundary errors are intentionally terse and sanitized by callers.
# ruff: noqa: TRY003

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_03 import (
    M2703_MAX_CANONICAL_REQUEST_BYTES,
    M2703_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityPipelineResult,
    OrchestrateComplexActivityPipelineRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2703Engine
from .service import M2703Service

_REQUEST_ADAPTER: Final = TypeAdapter(OrchestrateComplexActivityPipelineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityPipelineResult)
@dataclass(frozen=True, slots=True)
class ValidatedM2703Request:
    """Opaque request token issued by strict validation."""

    request: OrchestrateComplexActivityPipelineRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class M2703Plugin:
    """Plugin boundary requiring validation exactly once before execution."""

    def __init__(self, service: M2703Service | None = None) -> None:
        self._service = service or M2703Service(M2703Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M27-03",
            title="Reproducible complex-activity pipeline orchestrator",
            version="0.1.0-provisional",
            owner="Quality engineering",
            safety_class="S3",
            gate="G1",
            prohibited_outputs=(
                "protein/proteoform/isoform inference",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2703Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2703_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        elif isinstance(request, dict):
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request), strict=True)
        else:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        request_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        return ValidatedM2703Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=request_bytes,
        )

    def run(self, request: ValidatedM2703Request) -> ComplexActivityPipelineResult:
        if (
            not isinstance(request, ValidatedM2703Request)
            or request._seal is not self._seal
            or type(request.request) is not OrchestrateComplexActivityPipelineRequest
            or id(request.request) != request._request_identity
        ):
            raise TypeError("M27-03 run requires a validated request token")
        try:
            current_bytes = canonical_json_bytes(request.request.model_dump(mode="json"))
        except Exception as error:
            raise TypeError("M27-03 run requires a validated request token") from error
        if current_bytes != request._request_bytes:
            raise TypeError("M27-03 run requires a validated request token")
        return self._service._execute_validated(request.request)

    def verify(self, result: object, *, replay: bool = True) -> ComplexActivityPipelineResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2703_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(typed, replay=replay)


__all__ = ["M2703Plugin", "ValidatedM2703Request"]
