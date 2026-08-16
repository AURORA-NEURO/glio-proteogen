"""Strict parse-once plugin adapter for M20-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_07 import (
    M2007_MAX_CANONICAL_REQUEST_BYTES,
    ExportProteinSubtypeDownstreamContractRequest,
    ProteinSubtypeDownstreamExportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2007Engine, preflight_m2007_authorization
from .service import M2007Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteinSubtypeDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeDownstreamExportResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM2007Request:
    """Opaque request token issued by the strict parser."""

    request: ExportProteinSubtypeDownstreamContractRequest
    _seal: object


class M2007Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M2007Service | None = None) -> None:
        self._service = service or M2007Service(M2007Engine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M20-07",
            title="Downstream typed export",
            version="0.1.0-provisional",
            owner="Computational biology",
            safety_class="S2",
            gate="G3",
            prohibited_outputs=(
                "kinase activity",
                "generic all-omics fusion",
                "direct treatment recommendation",
                "identity or consent inference",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2007Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2007_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2007_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2007_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM2007Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM2007Request) -> ProteinSubtypeDownstreamExportResult:
        if not isinstance(request, ValidatedM2007Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeDownstreamExportResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M2007Plugin", "ValidatedM2007Request"]
