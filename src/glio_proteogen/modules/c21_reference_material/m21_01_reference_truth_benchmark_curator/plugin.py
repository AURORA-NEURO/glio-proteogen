"""Strict parse-once plugin boundary for M21-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_01 import (
    M2101_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivityReferenceTruthResult,
    CurateComplexActivityReferenceTruthRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2101_authorization

if TYPE_CHECKING:
    from .service import M2101Service

_REQUEST_ADAPTER: Final = TypeAdapter(CurateComplexActivityReferenceTruthRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M21-01",
    title="Reference truth and benchmark curator (provisional)",
    version="0.1.0-provisional",
    owner="Quality engineering",
    safety_class="S3",
    gate="G0",
    prohibited_outputs=(
        "issuer or review authority authentication",
        "protein, proteoform, subtype, or complex-activity inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "identity, consent, or missing-evidence inference",
        "unsupported or missing evidence converted to a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class ReferenceTruthSubmission:
    """Submission wrapper that keeps the input object opaque until validation."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2101Request:
    """Opaque capability proving strict M21-01 request validation."""

    request: CurateComplexActivityReferenceTruthRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2101Request,
        tuple[object, CurateComplexActivityReferenceTruthRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: CurateComplexActivityReferenceTruthRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="python"))


def _token_is_issued(token: ValidatedM2101Request, seal: object) -> bool:
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
        super().__init__("M21-01 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M21-01 validation requires a reference-truth submission")


class M2101Plugin(ModulePlugin[object, ValidatedM2101Request, ComplexActivityReferenceTruthResult]):
    """Expose M21-01 through validate-then-run without an authority bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2101Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2101Request:
        if not isinstance(request, ReferenceTruthSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2101_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2101_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2101Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(self, request: ValidatedM2101Request) -> ComplexActivityReferenceTruthResult:
        if (
            type(request) is not ValidatedM2101Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.execute(request.request)


__all__ = ["M2101Plugin", "ReferenceTruthSubmission", "ValidatedM2101Request"]
