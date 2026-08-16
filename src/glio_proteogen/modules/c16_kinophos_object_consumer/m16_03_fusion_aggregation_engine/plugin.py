"""Capability-gated plugin boundary for M16-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m16_03 import (
    M1603_MAX_CANONICAL_REQUEST_BYTES,
    FuseProteinRnaDiscordanceEvidenceRequest,
    ProteinRnaDiscordanceIntegratedEvidenceResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1603_authorization

if TYPE_CHECKING:
    from .service import M1603Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M16-03",
    title="Fusion and aggregation engine (provisional)",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "generic all-omics fusion or mutation of upstream evidence",
        "KINOPHOS kinase state or direct treatment recommendation",
        (
            "identity or consent inference, disagreement erasure, source relabeling, or "
            "unsupported-to-negative conversion"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1603Request:
    request: FuseProteinRnaDiscordanceEvidenceRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M16-03 execution requires a validated request token")


class M1603Plugin(
    ModulePlugin[
        object,
        ValidatedM1603Request,
        ProteinRnaDiscordanceIntegratedEvidenceResult,
    ]
):
    """Grant one immutable bounded component-specific fusion capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1603Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1603Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1603_MAX_CANONICAL_REQUEST_BYTES)
            typed = FuseProteinRnaDiscordanceEvidenceRequest.model_validate_json(
                serialized,
                strict=True,
            )
            preflight_m1603_authorization(typed)
        else:
            preflight_m1603_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1603Request(request=typed, _seal=_TOKEN_SEAL)

    def run(
        self,
        request: ValidatedM1603Request,
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        if type(request) is not ValidatedM1603Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceIntegratedEvidenceResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1603Plugin", "ValidatedM1603Request"]
