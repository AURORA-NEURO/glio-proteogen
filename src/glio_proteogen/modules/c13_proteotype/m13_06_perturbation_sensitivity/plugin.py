"""Capability-gated plugin boundary for M13-06."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from glio_proteogen.contracts.m13_06 import (
    M1306_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypePerturbationSensitivityResult,
    SimulateProteotypePerturbationRequest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity.service import (
        M1306Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M13-06",
    title="Variant-peptide perturbation and sensitivity simulator",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "kinase activity, all-omics fusion, treatment recommendation, or clinical advice",
        "subtype, mechanism, identity, consent, or upstream evidence inference",
        "unbounded responses, calibrated probabilities, or silent negative conversion",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedM1306Request:
    request: SimulateProteotypePerturbationRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M13-06 execution requires a validated request token")


class M1306Plugin(
    ModulePlugin[object, ValidatedM1306Request, ProteotypePerturbationSensitivityResult]
):
    """Grant one immutable bounded-simulation capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M1306Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1306Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            decoded = strict_json_loads(serialized, max_bytes=M1306_MAX_CANONICAL_REQUEST_BYTES)
            typed = self._service.validate_request(decoded)
        else:
            typed = self._service.validate_request(request)
        return ValidatedM1306Request(request=typed, _seal=_TOKEN_SEAL)

    def run(self, request: ValidatedM1306Request) -> ProteotypePerturbationSensitivityResult:
        if type(request) is not ValidatedM1306Request or request._seal is not _TOKEN_SEAL:
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M1306Plugin", "ValidatedM1306Request"]
