"""Strict parse-once plugin boundary for provisional M25-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_04 import (
    M2504_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeExternalTransportRequest,
    ProteotypeExternalTransportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2504Request:
    """Opaque capability proving strict M25-04 request validation."""

    request: EvaluateProteotypeExternalTransportRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2504Request,
        tuple[object, EvaluateProteotypeExternalTransportRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: EvaluateProteotypeExternalTransportRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2504Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = _canonical_request_bytes(token.request)
    except (TypeError, ValueError):
        return False
    return (
        snapshot is not None
        and snapshot[0] is seal
        and snapshot[1] is token.request
        and snapshot[2] == current
    )


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-04 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-04 validation requires a transport submission")


class M2504Plugin(ModulePlugin[object, ValidatedM2504Request, ProteotypeExternalTransportResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2504Service) -> None:
        self._service = service
        self._seal = object()

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
        validated = self._service.validate_request(candidate)
        token = ValidatedM2504Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: ValidatedM2504Request,
    ) -> ProteotypeExternalTransportResult:
        if (
            type(request) is not ValidatedM2504Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeExternalTransportResult,
    ) -> ProteotypeExternalTransportResult:
        return self._service.verify_replay(result)


__all__ = ["M2504Plugin", "TransportSubmission", "ValidatedM2504Request"]
