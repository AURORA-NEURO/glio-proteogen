"""Strict parse-once plugin boundary for provisional M25-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_04 import (
    M2504_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeExternalTransportRequest,
    ProteotypeExternalTransportResult,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2504_authorization

if TYPE_CHECKING:
    from .service import M2504Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteotypeExternalTransportRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M25-04",
    title="External transport evaluator (provisional)",
    version="0.1.0-provisional",
    owner="ML engineering",
    safety_class="S3",
    gate="G3",
    prohibited_outputs=(
        "proteotype or biological estimate",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, disagreement erasure, or unsupported-to-negative inference",
        "raw scientific-content traversal or upstream mutation",
    ),
)


@dataclass(frozen=True, slots=True)
class TransportSubmission:
    """Opaque submission wrapper for the strict request boundary."""

    request: object


@dataclass(frozen=True, slots=True)
class ValidatedM2504Request:
    """Opaque capability proving strict M25-04 request validation."""

    request: EvaluateProteotypeExternalTransportRequest


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-04 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-04 validation requires a transport submission")


class M2504Plugin(ModulePlugin[object, ValidatedM2504Request, ProteotypeExternalTransportResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_service",)

    def __init__(self, service: M2504Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2504Request:
        if not isinstance(request, TransportSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(candidate, max_bytes=M2504_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2504_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        return ValidatedM2504Request(request=self._service.validate_request(candidate))

    def run(
        self,
        request: ValidatedM2504Request,
    ) -> ProteotypeExternalTransportResult:
        if not isinstance(request, ValidatedM2504Request):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeExternalTransportResult,
    ) -> ProteotypeExternalTransportResult:
        return self._service.verify_replay(result)


__all__ = ["M2504Plugin", "TransportSubmission", "ValidatedM2504Request"]
