"""Strict parse-once plugin adapter for M21-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m21_08 import (
    M2108_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateComplexActivityEvidenceGateRequest,
    ComplexActivityEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2108Engine, M2108ReplayError, preflight_m2108_authorization
from .service import M2108Service

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateComplexActivityEvidenceGateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityEvidenceGateResult)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2108Request:
    """Opaque capability proving strict M21-08 request validation."""

    request: AdjudicateComplexActivityEvidenceGateRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2108Request,
        tuple[object, AdjudicateComplexActivityEvidenceGateRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: AdjudicateComplexActivityEvidenceGateRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2108Request, seal: object) -> bool:
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


class M2108TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M21-08 requires a token produced by this plugin")


class M2108Plugin:
    """Plugin enforcing validation exactly once before adjudication."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2108Service | None = None) -> None:
        self._service = service or M2108Service(M2108Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M21-08",
            title="Evidence gate and release adjudicator",
            version="0.1.0-provisional",
            owner="ML engineering",
            safety_class="S3",
            gate="G5",
            prohibited_outputs=(
                "complex-activity estimate",
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2108Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2108_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2108_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2108_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2108Request(request=typed, _seal=self._seal)
        _TOKENS[token] = (self._seal, typed, _canonical_request_bytes(typed))
        return token

    def run(self, request: ValidatedM2108Request) -> ComplexActivityEvidenceGateResult:
        if (
            type(request) is not ValidatedM2108Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise M2108TokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityEvidenceGateResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError) as error:
            raise M2108ReplayError from error
        return self._service.verify(validated, replay=replay)


__all__ = ["M2108Plugin", "M2108TokenError", "ValidatedM2108Request"]
