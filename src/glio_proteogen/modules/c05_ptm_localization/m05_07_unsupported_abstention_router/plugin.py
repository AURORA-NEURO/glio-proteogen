"""Strict validate-then-run plugin boundary for M05-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m05_07 import (
    M0507_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router.engine import (  # noqa: E501
    _validate_json_request,
)

if TYPE_CHECKING:
    from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router.service import (  # noqa: E501
        M0507Service,
    )

_TOKEN_SEAL: Final = object()
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M05-07",
    title="PTM-localization unsupported-case and abstention router",
    version="1.0.0",
    owner="Bioinformatics",
    safety_class="S2",
    gate="G1",
    prohibited_outputs=(
        "negative scientific findings from missing, unknown, or unsupported evidence",
        "variant-peptide, proteotype, kinase-state, or treatment recommendation outputs",
        "generic all-omics fusion, identity or consent inference, or evidence relabeling",
    ),
)


@dataclass(frozen=True, slots=True)
class M0507Submission:
    """Plugin submission wrapper retained for a stable module boundary."""

    request: object


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM0507Request:
    request: RoutePtmLocalizationSupportRequest
    _seal: object


_ISSUED_TOKENS: Final[
    WeakKeyDictionary[ValidatedM0507Request, tuple[RoutePtmLocalizationSupportRequest, str]]
] = WeakKeyDictionary()


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-07 execution requires a validated request token")


class M0507Plugin(ModulePlugin[object, ValidatedM0507Request, PtmLocalizationSupportRouteResult]):
    """Grant one immutable M05-07 execution capability."""

    __slots__ = ("_service",)

    def __init__(self, service: M0507Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM0507Request:
        candidate = request.request if type(request) is M0507Submission else request
        if isinstance(candidate, bytes | bytearray | str):
            raw = candidate
            decoded = strict_json_loads(raw, max_bytes=M0507_MAX_CANONICAL_REQUEST_BYTES)
            typed = _validate_json_request(decoded, cast("bytes | str", raw))
        else:
            typed = self._service.validate_request(candidate)
        token = ValidatedM0507Request(request=typed, _seal=_TOKEN_SEAL)
        _ISSUED_TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM0507Request) -> PtmLocalizationSupportRouteResult:
        snapshot = _ISSUED_TOKENS.get(request) if type(request) is ValidatedM0507Request else None
        if (
            snapshot is None
            or request._seal is not _TOKEN_SEAL
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise _InvalidExecutionTokenError
        return self._service._execute_validated(request.request)


__all__ = ["M0507Plugin", "M0507Submission", "ValidatedM0507Request"]
