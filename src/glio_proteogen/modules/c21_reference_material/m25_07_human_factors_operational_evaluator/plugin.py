"""Strict parse-once plugin boundary for provisional M25-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_07 import (
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeHumanFactorsRequest,
    ProteotypeHumanFactorsResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2507_authorization

if TYPE_CHECKING:
    from .service import M2507Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeHumanFactorsRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-07",
    title="Human-factors and operational evaluator (provisional)",
    version="0.1.0-provisional",
    owner="Data engineering",
    safety_class="S3",
    gate="G4",
    prohibited_outputs=(
        "identity, consent, treatment, or clinical eligibility inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or unsupported-to-negative conversion",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class HumanFactorsSubmission:
    """Opaque submission wrapper for strict request validation."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2507Request:
    """Opaque capability proving strict M25-07 request validation."""

    request: EvaluateProteotypeHumanFactorsRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-07 validation requires an operational submission")


class M2507Plugin(ModulePlugin[object, ValidatedM2507Request, ProteotypeHumanFactorsResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2507Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2507Request:
        if not isinstance(request, HumanFactorsSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2507_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2507_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2507Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2507Request,
    ) -> ProteotypeHumanFactorsResult:
        if not isinstance(request, ValidatedM2507Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeHumanFactorsResult,
    ) -> ProteotypeHumanFactorsResult:
        return self._service.verify_replay(result)


__all__ = ["HumanFactorsSubmission", "M2507Plugin", "ValidatedM2507Request"]
