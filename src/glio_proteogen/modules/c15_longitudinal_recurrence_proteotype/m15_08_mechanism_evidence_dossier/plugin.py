"""Capability-gated plugin boundary for M15-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m15_08 import (
    M1508_MAX_CANONICAL_REQUEST_BYTES,
    AssembleComplexActivityMechanismDossierRequest,
    ComplexActivityMechanismDossierResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1508_authorization

if TYPE_CHECKING:
    from .service import M1508Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M15-08",
    title="Mechanism evidence dossier (provisional)",
    version="0.1.0-provisional",
    owner="Clinical science",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "unfrozen mechanism or proteogenomic-state inference from opaque references",
        "KINOPHOS kinase state, generic all-omics fusion, or direct treatment recommendation",
        (
            "identity or consent inference, upstream relabeling, disagreement erasure, or "
            "unsupported-to-negative conversion"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1508Request:
    request: AssembleComplexActivityMechanismDossierRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-08 execution requires a validated request token")


class M1508Plugin(
    ModulePlugin[
        object,
        ValidatedM1508Request,
        ComplexActivityMechanismDossierResult,
    ]
):
    """Grant one immutable bounded dossier-assembly capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1508Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1508Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1508_MAX_CANONICAL_REQUEST_BYTES)
            typed = AssembleComplexActivityMechanismDossierRequest.model_validate_json(
                serialized,
                strict=True,
            )
            preflight_m1508_authorization(typed)
        else:
            preflight_m1508_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1508Request(request=typed, _seal=_TOKEN_SEAL)

    def run(
        self,
        request: ValidatedM1508Request,
    ) -> ComplexActivityMechanismDossierResult:
        if type(request) is not ValidatedM1508Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismDossierResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1508Plugin", "ValidatedM1508Request"]
