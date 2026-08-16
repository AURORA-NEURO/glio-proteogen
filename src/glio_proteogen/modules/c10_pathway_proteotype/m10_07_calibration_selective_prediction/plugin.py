"""Sealed parse-once plugin boundary for provisional M10-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_07 import (
    M1007_MAX_CANONICAL_REQUEST_BYTES,
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    canonical_request_digest,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import BuiltM1007Result

if TYPE_CHECKING:
    from .service import M1007Service

_TOKEN_SEAL: Final = object()
_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateProteinRnaDiscordanceSelectivePredictionRequest)
_DESCRIPTOR: Final = ModuleDescriptor(
    module_id="GLIO-PROTEOGEN-M10-07",
    title="calibration and selective prediction (provisional)",
    version="0.1.0-provisional",
    owner="Platform engineering",
    safety_class="S2",
    gate="G3",
    prohibited_outputs=(
        "kinase activity, generic all-omics fusion, or direct treatment recommendation",
        "parent protein-RNA discordance emission, identity or consent inference",
        "unsupported-to-negative conversion or external-content traversal",
    ),
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1007Request:
    request: CalibrateProteinRnaDiscordanceSelectivePredictionRequest
    _seal: object


class M1007TokenError(TypeError):
    """Raised when execution is attempted without a sealed validation token."""

    def __init__(self) -> None:
        super().__init__("M10-07 execution requires a validated request token")


_TOKENS: Final[WeakKeyDictionary[ValidatedM1007Request, tuple[object, str]]] = WeakKeyDictionary()


class M1007Plugin(ModulePlugin[object, ValidatedM1007Request, BuiltM1007Result]):
    __slots__ = ("_service",)

    def __init__(self, service: M1007Service) -> None:
        self._service = service

    def descriptor(self) -> ModuleDescriptor:
        return _DESCRIPTOR

    def validate(self, request: object) -> ValidatedM1007Request:
        if type(request) in {bytes, bytearray, str}:
            serialized = cast("bytes | bytearray | str", request)
            strict_json_loads(serialized, max_bytes=M1007_MAX_CANONICAL_REQUEST_BYTES)
            typed = _REQUEST_ADAPTER.validate_json(serialized, strict=True)
        else:
            typed = self._service.validate_request(request)
        token = ValidatedM1007Request(request=typed, _seal=_TOKEN_SEAL)
        _TOKENS[token] = (typed, canonical_request_digest(typed))
        return token

    def run(self, request: ValidatedM1007Request) -> BuiltM1007Result:
        try:
            snapshot = _TOKENS.get(request)
        except TypeError as error:
            raise M1007TokenError from error
        if (
            type(request) is not ValidatedM1007Request
            or request._seal is not _TOKEN_SEAL
            or snapshot is None
            or snapshot[0] is not request.request
            or snapshot[1] != canonical_request_digest(request.request)
        ):
            raise M1007TokenError
        return self._service.execute(request.request)


__all__ = ["M1007Plugin", "ValidatedM1007Request"]
