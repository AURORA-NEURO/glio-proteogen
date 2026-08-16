"""Strict parse-once plugin boundary for M10-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m10_03 import (
    EstimateProteinRnaDiscordanceBaselineRequest,
    ProteinRnaDiscordanceBaselineResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin

from .engine import _validate_serialized_json_request

if TYPE_CHECKING:
    from .service import M1003Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-03",
    title="Pathway/proteotype mature baseline estimator",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "kinase activity",
        "generic all-omics fusion",
        "treatment recommendation",
        "identity or consent inference",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1003Request:
    request: EstimateProteinRnaDiscordanceBaselineRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-03 execution requires a validated request token")


class M1003Plugin(ModulePlugin[object, ValidatedM1003Request, ProteinRnaDiscordanceBaselineResult]):
    __slots__ = ("_service",)

    def __init__(self, service: M1003Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1003Request:
        if type(request) in {bytes, bytearray, str}:
            typed = _validate_serialized_json_request(cast("bytes | bytearray | str", request))
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1003Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1003Request) -> ProteinRnaDiscordanceBaselineResult:
        if type(request) is not ValidatedM1003Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1003Plugin", "ValidatedM1003Request"]
