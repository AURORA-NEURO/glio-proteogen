"""Strict validate-then-run plugin for M02-07 joint support routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_07 import (
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router.engine import (
    preflight_identification_support_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c02_identification_qc.m02_07_support_router.service import (
        M0207Service,
    )

_REQUEST_ADAPTER: Final = TypeAdapter(RouteIdentificationSupportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M02-07",
    title="Unsupported-case and abstention router",
    version="1.0.0",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "protein subtype, proteotype, or biological inference",
        "kinase-state ownership or generic all-omics fusion",
        "upstream quality, harmonization, evidence, identity, or consent mutation",
        "missing evidence interpreted as a negative finding",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0207Request:
    """Opaque capability proving that the M02-07 boundary accepted the request."""

    request: RouteIdentificationSupportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M02-07 execution requires a validated request token")


class M0207Plugin(ModulePlugin[object, ValidatedM0207Request, IdentificationSupportRouteResult]):
    """Expose M02-07 through the common plugin ABI without widening authority."""

    __slots__ = ("_service",)

    def __init__(self, service: M0207Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0207Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            preflight_identification_support_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0207Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0207Request) -> IdentificationSupportRouteResult:
        if not isinstance(request, ValidatedM0207Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0207Plugin", "ValidatedM0207Request"]
