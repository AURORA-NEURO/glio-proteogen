"""Strict validate-then-run plugin for provisional M07-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m07_04 import (
    M0704_MAX_CANONICAL_REQUEST_BYTES,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimateCopyNumberDosageProbabilisticResult,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_probabilistic_estimator_authorization

if TYPE_CHECKING:
    from .service import M0704Service

_TOKEN_SEAL: Final = object()
_ISSUED_TOKENS: Final[WeakKeyDictionary[ValidatedM0704Request, tuple[object, str]]] = (
    WeakKeyDictionary()
)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M07-04",
    title="Copy-number dosage probabilistic/advanced estimator",
    version="0.1.0-provisional",
    owner="Computational biology",
    safety_class="S2",
    gate="G2",
    prohibited_outputs=(
        "calibrated clinical posterior or treatment recommendation",
        "kinase activity, generic all-omics fusion, or parent proteotype emission",
        "unsupported-to-negative conversion or untyped missing values",
        "upstream mutation, relabeling, identity, consent, or provenance changes",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0704Request:
    """Opaque capability proving strict M07-04 request validation."""

    request: EstimateCopyNumberDosageProbabilisticRequest
    _seal: object


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M07-04 execution requires a validated request token")


class M0704Plugin(
    ModulePlugin[
        object,
        ValidatedM0704Request,
        EstimateCopyNumberDosageProbabilisticResult,
    ]
):
    """Expose M07-04 only after parse-once validation and authorization."""

    __slots__ = ("_service",)

    def __init__(self, service: M0704Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0704Request:
        if isinstance(request, bytes | bytearray | str):
            decoded = strict_json_loads(request, max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES)
            preflight_probabilistic_estimator_authorization(decoded)
        typed = self._service.validate_request(request)
        token = ValidatedM0704Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0704Request) -> EstimateCopyNumberDosageProbabilisticResult:
        snapshot = _ISSUED_TOKENS.get(request)
        if (
            type(request) is not ValidatedM0704Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> EstimateCopyNumberDosageProbabilisticResult:
        return self._service.verify(result, replay=replay)


__all__ = ["M0704Plugin", "ValidatedM0704Request"]
