"""Strict parse-once plugin adapter for M19-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_07 import (
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    M1907_MAX_CANONICAL_RESULT_BYTES,
    ExportProteotypeDownstreamContractRequest,
    ProteotypeDownstreamExportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1907Engine, preflight_m1907_authorization
from .service import M1907Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteotypeDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeDownstreamExportResult)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1907Request:
    """Opaque capability proving strict M19-07 request validation."""

    request: ExportProteotypeDownstreamContractRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1907Request,
        tuple[object, ExportProteotypeDownstreamContractRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: ExportProteotypeDownstreamContractRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM1907Request, seal: object) -> bool:
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


class M1907TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M19-07 requires a token produced by this plugin")


class M1907Plugin:
    """Plugin enforcing validation exactly once before execution."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1907Service | None = None) -> None:
        self._service = service or M1907Service(M1907Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M19-07",
            title="Downstream typed export",
            version="0.1.0-provisional",
            owner="Scientific engineering",
            safety_class="S2",
            gate="G3",
            prohibited_outputs=(
                "kinase activity",
                "generic all-omics fusion",
                "direct treatment recommendation",
                "identity or consent inference",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM1907Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1907_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m1907_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m1907_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM1907Request(request=typed, _seal=self._seal)
        _TOKENS[token] = (self._seal, typed, _canonical_request_bytes(typed))
        return token

    def run(self, request: ValidatedM1907Request) -> ProteotypeDownstreamExportResult:
        if (
            type(request) is not ValidatedM1907Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise M1907TokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteotypeDownstreamExportResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M1907_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(typed, replay=replay)


__all__ = ["M1907Plugin", "M1907TokenError", "ValidatedM1907Request"]
