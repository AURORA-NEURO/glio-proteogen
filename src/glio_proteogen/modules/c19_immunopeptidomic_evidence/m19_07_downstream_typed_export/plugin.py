"""Strict parse-once plugin adapter for M19-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_07 import (
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    ExportProteotypeDownstreamContractRequest,
    ProteotypeDownstreamExportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1907Engine, preflight_m1907_authorization
from .service import M1907Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteotypeDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeDownstreamExportResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM1907Request:
    """Opaque request token issued by the strict parser."""

    request: ExportProteotypeDownstreamContractRequest
    _seal: object


class M1907Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M1907Service | None = None) -> None:
        self._service = service or M1907Service(M1907Engine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M19-07",
            title="Downstream typed export",
            version="0.1.0-provisional",
            owner="Scientific engineering",
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

    def validate(self, request: object) -> ValidatedM1907Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1907_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m1907_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m1907_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM1907Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM1907Request) -> ProteotypeDownstreamExportResult:
        if not isinstance(request, ValidatedM1907Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeDownstreamExportResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(typed, replay=replay)


__all__ = ["M1907Plugin", "ValidatedM1907Request"]
