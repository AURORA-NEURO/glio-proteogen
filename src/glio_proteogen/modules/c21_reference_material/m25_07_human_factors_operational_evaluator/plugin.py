"""Strict parse-once plugin boundary for provisional M25-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_07 import (
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteotypeHumanFactorsRequest,
    ProteotypeHumanFactorsResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2507Request:
    """Opaque capability proving strict M25-07 request validation."""

    request: EvaluateProteotypeHumanFactorsRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2507Request,
        tuple[object, EvaluateProteotypeHumanFactorsRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: EvaluateProteotypeHumanFactorsRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2507Request, seal: object) -> bool:
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
        super().__init__("M25-07 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M25-07 validation requires an operational submission")


class M2507Plugin(ModulePlugin[object, ValidatedM2507Request, ProteotypeHumanFactorsResult]):
    """Expose validate-then-run without an authority or parse bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2507Service) -> None:
        self._service = service
        self._seal = object()

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
        validated = self._service.validate_request(candidate)
        token = ValidatedM2507Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: ValidatedM2507Request,
    ) -> ProteotypeHumanFactorsResult:
        if (
            type(request) is not ValidatedM2507Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)

    def replay(
        self,
        result: ProteotypeHumanFactorsResult,
    ) -> ProteotypeHumanFactorsResult:
        return self._service.verify_replay(result)


__all__ = ["HumanFactorsSubmission", "M2507Plugin", "ValidatedM2507Request"]
