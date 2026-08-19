"""Capability-gated plugin boundary for M14-03."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m14_03 import (
    M1403_MAX_CANONICAL_REQUEST_BYTES,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    ProteinSubtypeMechanisticFeatureResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m1403_authorization

if TYPE_CHECKING:
    from .service import M1403Service

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M14-03",
    title="Mechanistic feature constructor (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "mechanistic or clinical inference from opaque artifact references",
        (
            "kinase activity, all-omics fusion, treatment recommendation, identity or "
            "consent inference"
        ),
        "unsupported-to-negative conversion, mutation relabeling, or disagreement erasure",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1403Request:
    request: ConstructProteinSubtypeMechanisticFeaturesRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-03 execution requires a validated request token")


class M1403Plugin(
    ModulePlugin[object, ValidatedM1403Request, ProteinSubtypeMechanisticFeatureResult]
):
    """Grant one immutable bounded construction capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1403Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1403Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            parsed = strict_json_loads(
                serialized,
                max_bytes=M1403_MAX_CANONICAL_REQUEST_BYTES,
            )
            # Check caller controls on the bounded decoded document before
            # traversing or issuing a token for any nested configuration.
            preflight_m1403_authorization(parsed)
            typed = ConstructProteinSubtypeMechanisticFeaturesRequest.model_validate_json(
                serialized,
                strict=True,
            )
        else:
            preflight_m1403_authorization(request)
            typed = self._service.validate_request(request)
        return ValidatedM1403Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1403Request) -> ProteinSubtypeMechanisticFeatureResult:
        if type(request) is not ValidatedM1403Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M1403Plugin", "ValidatedM1403Request"]
