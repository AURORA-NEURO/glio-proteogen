"""Strict parse-once plugin adapter for the provisional M26-03 ABI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_03 import (
    M2603_MAX_CANONICAL_REQUEST_BYTES,
    M2603_MAX_CANONICAL_RESULT_BYTES,
    ExecuteProteinSubtypeWorkflowRequest,
    ProteinSubtypeExecutionResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2603Engine, preflight_m2603_authorization
from .service import M2603Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExecuteProteinSubtypeWorkflowRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeExecutionResult)
@dataclass(frozen=True, slots=True)
class ValidatedM2603Request:
    """Opaque request token issued by the strict parser."""

    request: ExecuteProteinSubtypeWorkflowRequest
    _seal: object
    _request_identity: int = 0
    _request_bytes: bytes = b""


class M2603Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M2603Service | None = None) -> None:
        self._service = service or M2603Service(M2603Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M26-03",
            title="Reproducible pipeline orchestrator",
            version="0.1.0-provisional",
            owner="ML engineering",
            safety_class="S3",
            gate="G1",
            prohibited_outputs=(
                "protein subtype estimate",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2603Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2603_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2603_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2603_authorization(request)
            typed = self._service.validate_request(request)
        request_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        return ValidatedM2603Request(
            request=typed,
            _seal=self._seal,
            _request_identity=id(typed),
            _request_bytes=request_bytes,
        )

    def run(self, request: ValidatedM2603Request) -> ProteinSubtypeExecutionResult:
        if (
            not isinstance(request, ValidatedM2603Request)
            or request._seal is not self._seal
            or type(request.request) is not ExecuteProteinSubtypeWorkflowRequest
            or id(request.request) != request._request_identity
        ):
            raise TypeError
        try:
            current_bytes = canonical_json_bytes(request.request.model_dump(mode="json"))
        except Exception as error:
            raise TypeError from error
        if current_bytes != request._request_bytes:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(self, result: object, *, replay: bool = True) -> ProteinSubtypeExecutionResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2603_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(typed, replay=replay)


__all__ = ["M2603Plugin", "ValidatedM2603Request"]
