"""Strict parse-once plugin adapter for M18-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_07 import (
    M1807_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelDownstreamExportResult,
    ExportBiomarkerPanelDownstreamContractRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1807Engine, preflight_m1807_authorization
from .service import M1807Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportBiomarkerPanelDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelDownstreamExportResult)
_SEAL: Final = object()


@dataclass(frozen=True, slots=True)
class ValidatedM1807Request:
    """Opaque request token issued by the strict parser."""

    request: ExportBiomarkerPanelDownstreamContractRequest
    _seal: object


class M1807Plugin:
    """Plugin enforcing validation exactly once before execution."""

    def __init__(self, service: M1807Service | None = None) -> None:
        self._service = service or M1807Service(M1807Engine())

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M18-07",
            title="Downstream typed export",
            version="0.1.0-provisional",
            owner="Platform engineering",
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

    def validate(self, request: object) -> ValidatedM1807Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1807_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m1807_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m1807_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return ValidatedM1807Request(request=typed, _seal=_SEAL)

    def run(self, request: ValidatedM1807Request) -> BiomarkerPanelDownstreamExportResult:
        if not isinstance(request, ValidatedM1807Request) or request._seal is not _SEAL:
            raise TypeError
        return self._service.execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelDownstreamExportResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M1807Plugin", "ValidatedM1807Request"]
