"""Strict validate-then-run plugin boundary for M01-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_07 import RouteSupportRequest, SupportRoutingResult
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.engine import (
    preflight_support_routing_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_07_support_router.service import (
        M0107Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[RouteSupportRequest]] = TypeAdapter(RouteSupportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-07",
    title="Unsupported-case and abstention router",
    version="1.0.0",
    owner="Data engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "negative scientific finding from missing or unknown evidence",
        "proteotype or kinase-state inference",
        "generic omics fusion",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0107Request:
    request: RouteSupportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-07 execution requires a validated request token")


class M0107Plugin(ModulePlugin[object, ValidatedM0107Request, SupportRoutingResult]):
    """Expose strict parse, authorization, validation, and execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0107Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0107Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            candidate = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            preflight_support_routing_authorization(candidate)
            validated = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        else:
            preflight_support_routing_authorization(candidate)
            validated = _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        return ValidatedM0107Request(request=self._service.validate_request(validated))

    def run(self, request: ValidatedM0107Request) -> SupportRoutingResult:
        if not isinstance(request, ValidatedM0107Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0107Plugin", "ValidatedM0107Request"]
