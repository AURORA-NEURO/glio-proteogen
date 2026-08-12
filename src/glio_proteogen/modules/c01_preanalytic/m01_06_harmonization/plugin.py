"""Strict validate-then-run plugin boundary for M01-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_06 import HarmonizationResult, HarmonizeObservationsRequest
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.engine import (
    preflight_harmonization_authorization,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.service import (
        M0106Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[HarmonizeObservationsRequest]] = TypeAdapter(
    HarmonizeObservationsRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-06",
    title="Harmonization and normalization engine",
    version="1.0.0",
    owner="Clinical science",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw payload parsing or retention",
        "missing or censored value imputation",
        "kinase-state or treatment inference",
        "unconfigured learned normalization",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0106Request:
    request: HarmonizeObservationsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-06 execution requires a validated request token")


class M0106Plugin(ModulePlugin[object, ValidatedM0106Request, HarmonizationResult]):
    """Expose strict parse, authorization, validation, and execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0106Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0106Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            candidate = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            preflight_harmonization_authorization(candidate)
            validated = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        else:
            preflight_harmonization_authorization(candidate)
            validated = _REQUEST_ADAPTER.validate_python(candidate, strict=True)
        return ValidatedM0106Request(request=self._service.validate_request(validated))

    def run(self, request: ValidatedM0106Request) -> HarmonizationResult:
        if not isinstance(request, ValidatedM0106Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0106Plugin", "ValidatedM0106Request"]
