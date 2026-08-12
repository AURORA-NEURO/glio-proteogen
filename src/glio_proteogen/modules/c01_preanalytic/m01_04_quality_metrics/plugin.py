"""Strict validate-then-run plugin boundary for M01-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_04 import ComputeQualityMetricsRequest, QualityProfile
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES, strict_json_loads

if TYPE_CHECKING:
    from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
        M0104Service,
    )

_REQUEST_ADAPTER: Final[TypeAdapter[ComputeQualityMetricsRequest]] = TypeAdapter(
    ComputeQualityMetricsRequest
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M01-04",
    title="Quality metric computation",
    version="1.0.0",
    owner="ML engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "raw assay parsing or payload retention",
        "proteotype or kinase-state inference",
        "upstream evidence or identity mutation",
        "missing evidence interpreted as a negative finding",
        "clinical or treatment recommendation",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM0104Request:
    request: ComputeQualityMetricsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M01-04 execution requires a validated request token")


class M0104Plugin(ModulePlugin[object, ValidatedM0104Request, QualityProfile]):
    """Expose strict parse, validate, and revalidated execution phases."""

    __slots__ = ("_service",)

    def __init__(self, service: M0104Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0104Request:
        candidate = request
        if isinstance(candidate, bytes | bytearray | str):
            strict_json_loads(candidate, max_bytes=MAX_JSON_BYTES)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM0104Request(request=self._service.validate_request(candidate))

    def run(self, request: ValidatedM0104Request) -> QualityProfile:
        if not isinstance(request, ValidatedM0104Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M0104Plugin", "ValidatedM0104Request"]
