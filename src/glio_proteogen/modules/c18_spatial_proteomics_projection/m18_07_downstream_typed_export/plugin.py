"""Strict parse-once plugin adapter for M18-07."""

from __future__ import annotations

from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_07 import (
    M1807_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelDownstreamExportResult,
    ExportBiomarkerPanelDownstreamContractRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1807Engine, preflight_m1807_authorization
from .service import M1807Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportBiomarkerPanelDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelDownstreamExportResult)


class ValidatedM1807Request:
    """Opaque token coupling one validated request to one plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: ExportBiomarkerPanelDownstreamContractRequest, _seal: object
    ) -> None:
        self.request = request
        self._seal = _seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1807Request,
        tuple[object, ExportBiomarkerPanelDownstreamContractRequest, bytes],
    ]
] = WeakKeyDictionary()


class M1807TokenError(TypeError):
    """A token was forged, mutated, or issued by another plugin instance."""

    def __init__(self) -> None:
        super().__init__("M18-07 requires a validated request token")


class M1807Plugin:
    """Plugin enforcing validation exactly once before execution."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1807Service | None = None) -> None:
        self._service = service or M1807Service(M1807Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M18-07",
            title="Downstream typed export",
            version="0.1.0-provisional",
            owner="Platform engineering",
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

    def validate(self, request: object) -> ValidatedM1807Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M1807_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m1807_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m1807_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM1807Request(typed, self._seal)
        _TOKENS[token] = (self._seal, typed, canonical_json_bytes(typed))
        return token

    def run(self, request: ValidatedM1807Request) -> BiomarkerPanelDownstreamExportResult:
        if not isinstance(request, ValidatedM1807Request):
            raise M1807TokenError
        snapshot = _TOKENS.get(request)
        if snapshot is None or snapshot[0] is not self._seal or request._seal is not self._seal:
            raise M1807TokenError
        if snapshot[1] is not request.request:
            raise M1807TokenError
        try:
            current_bytes = canonical_json_bytes(request.request)
        except (TypeError, ValueError) as error:
            raise M1807TokenError from error
        if current_bytes != snapshot[2]:
            raise M1807TokenError
        return self._service._execute_validated(snapshot[1])

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelDownstreamExportResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M1807Plugin", "M1807TokenError", "ValidatedM1807Request"]
