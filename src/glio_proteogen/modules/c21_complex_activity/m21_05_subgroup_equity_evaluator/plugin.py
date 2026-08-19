"""Strict parse-once plugin adapter for M21-05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_05 import (
    M2105_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySubgroupEvaluationResult,
    EvaluateComplexActivitySubgroupEquityRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.plugin import ModuleDescriptor
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2105Engine, preflight_m2105_authorization
from .service import M2105Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivitySubgroupEquityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySubgroupEvaluationResult)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2105Request:
    """Opaque capability proving strict M21-05 request validation."""

    request: EvaluateComplexActivitySubgroupEquityRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2105Request,
        tuple[object, EvaluateComplexActivitySubgroupEquityRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: EvaluateComplexActivitySubgroupEquityRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2105Request, seal: object) -> bool:
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


class M2105TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M21-05 requires a token produced by this plugin")


class M2105Plugin:
    """Plugin enforcing validation exactly once before execution."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M2105Service | None = None) -> None:
        self._service = service or M2105Service(M2105Engine())
        self._seal = object()

    def descriptor(self) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="GLIO-PROTEOGEN-M21-05",
            title="Subgroup equity evaluator",
            version="0.1.0-provisional",
            owner="Scientific engineering",
            safety_class="S3",
            gate="G3",
            prohibited_outputs=(
                "identity or consent inference",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "unsupported negative finding",
            ),
        )

    def validate(self, request: object) -> ValidatedM2105Request:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2105_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2105_authorization(decoded)
            typed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        else:
            preflight_m2105_authorization(request)
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2105Request(request=typed, _seal=self._seal)
        _TOKENS[token] = (self._seal, typed, _canonical_request_bytes(typed))
        return token

    def run(self, request: ValidatedM2105Request) -> ComplexActivitySubgroupEvaluationResult:
        if (
            type(request) is not ValidatedM2105Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise M2105TokenError
        return self._service._execute_validated(request.request)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivitySubgroupEvaluationResult:
        _RESULT_ADAPTER.validate_python(result, strict=True)
        return self._service.verify(result, replay=replay)


__all__ = ["M2105Plugin", "M2105TokenError", "ValidatedM2105Request"]
