"""Strict parse-once M20-06 plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_06 import (
    M2006_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteinSubtypeQueueRequest,
    ProteinSubtypeAdjudicationResult,
    canonical_request_bytes,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import preflight_m2006_authorization

if TYPE_CHECKING:
    from .service import M2006Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateProteinSubtypeQueueRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M20-06",
    title="Reviewer discrepancy adjudication (provisional)",
    version="0.1.0-provisional",
    owner="Scientific engineering",
    safety_class="S2",
    gate="G4",
    prohibited_outputs=(
        "protein-subtype inference or identity inference",
        "KINOPHOS kinase-state ownership",
        "generic all-omics fusion or treatment recommendation",
        "upstream evidence mutation or disagreement erasure",
        "unsupported or missing evidence converted to a negative finding",
    ),
)


@dataclass(frozen=True, slots=True)
class AdjudicationSubmission:
    """Opaque submission wrapper that delays parsing until validation."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2006Request:
    """Opaque capability proving strict M20-06 request validation."""

    request: AdjudicateProteinSubtypeQueueRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2006Request,
        tuple[object, AdjudicateProteinSubtypeQueueRequest, bytes],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM2006Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = canonical_request_bytes(token.request)
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
        super().__init__("M20-06 execution requires a validated request token")


class _InvalidSubmissionError(TypeError):
    def __init__(self) -> None:
        super().__init__("M20-06 validation requires an adjudication submission")


class M2006Plugin(ModulePlugin[object, ValidatedM2006Request, ProteinSubtypeAdjudicationResult]):
    """Expose M20-06 through validate-then-run without an authority bypass."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2006Service) -> None:
        self._service = service
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM2006Request:
        if not isinstance(request, AdjudicationSubmission):
            raise _InvalidSubmissionError
        candidate = request.request
        if isinstance(candidate, bytes | bytearray | str):
            decoded = strict_json_loads(
                candidate,
                max_bytes=M2006_MAX_CANONICAL_REQUEST_BYTES,
            )
            preflight_m2006_authorization(decoded)
            candidate = _REQUEST_ADAPTER.validate_json(candidate, strict=True)
        validated = self._service.validate_request(candidate)
        token = ValidatedM2006Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_bytes(validated))
        return token

    def run(self, request: ValidatedM2006Request) -> ProteinSubtypeAdjudicationResult:
        if (
            type(request) is not ValidatedM2006Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise _InvalidExecutionTokenError
        return self._service.adjudicate(request.request)

    def replay(self, result: ProteinSubtypeAdjudicationResult) -> ProteinSubtypeAdjudicationResult:
        return self._service.replay(result)


__all__ = ["AdjudicationSubmission", "M2006Plugin", "ValidatedM2006Request"]
