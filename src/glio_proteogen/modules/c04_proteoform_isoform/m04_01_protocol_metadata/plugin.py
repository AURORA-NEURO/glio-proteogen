"""Strict validate-then-run plugin boundary for M04-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_01 import (
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteoformProtocolRequest,
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata.engine import (
    preflight_proteoform_protocol_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata.service import (
        M0401Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteoformProtocolRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M04-01",
    title="Proteoform/isoform protocol and metadata specification",
    version="1.0.0",
    owner="ML engineering",
    safety_class="S2",
    gate="G0",
    prohibited_outputs=(
        "proteoform, isoform, or modification-localization inference",
        "protein-RNA discordance, proteogenomic-state, proteotype, or subtype emission",
        "kinase-activity inference or generic all-omics fusion",
        "treatment or clinical recommendation",
        "mutation of upstream evidence or inference of identity or consent",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0401Request:
    """Opaque capability proving that M04-01 accepted the request boundary."""

    request: EvaluateProteoformProtocolRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-01 execution requires a validated request token")


class M0401Plugin(
    ModulePlugin[
        object,
        ValidatedM0401Request,
        ProteoformProtocolConformanceResult,
    ]
):
    """Expose declaration conformance without widening scientific authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0401Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0401Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M0401_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_proteoform_protocol_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0401Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM0401Request,
    ) -> ProteoformProtocolConformanceResult:
        if not isinstance(request, ValidatedM0401Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0401Plugin", "ValidatedM0401Request"]
