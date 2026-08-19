"""Strict JSON plugin boundary for M19-01."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_01 import ResolveProteotypeUpstreamContractsRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1901Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_01 import (
        ProteotypeUpstreamResolutionResult,
    )

_REQUEST_ADAPTER: TypeAdapter[ResolveProteotypeUpstreamContractsRequest] = TypeAdapter(
    ResolveProteotypeUpstreamContractsRequest
)

_MAX_JSON_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class M1901PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-01"
    operation: str = "resolve_proteotype_upstream_contracts"
    output_media_type: str = "application/vnd.glio-proteogen.m19-01+json"
    parent_target: str = "proteotype"
    owner: str = "Bioinformatics"
    safety_class: str = "S2"
    gate: str = "G0"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_discovery: bool = True
    typed_rejections: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1901Request:
    """Opaque capability proving strict M19-01 request validation."""

    request: ResolveProteotypeUpstreamContractsRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1901Request,
        tuple[object, ResolveProteotypeUpstreamContractsRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: ResolveProteotypeUpstreamContractsRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM1901Request, seal: object) -> bool:
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


class M1901TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M19-01 requires a token produced by this plugin")


class M1901Plugin:
    """Expose only strict request resolution and exact replay."""

    __slots__ = ("_engine", "_seal")

    def __init__(self) -> None:
        self._engine = M1901Engine()
        self._seal = object()

    @property
    def descriptor(self) -> M1901PluginDescriptor:
        return M1901PluginDescriptor()

    def validate_json(self, payload: str | bytes) -> ResolveProteotypeUpstreamContractsRequest:
        raw = payload.encode() if isinstance(payload, str) else payload
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("M19-01 request exceeds canonical size limit")  # noqa: TRY003
        try:
            document = strict_json_loads(raw, max_bytes=_MAX_JSON_BYTES)
        except StrictJsonError as exc:
            raise ValueError("M19-01 request must be valid JSON") from exc  # noqa: TRY003
        parsed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(document), strict=True)
        return self._engine.validate_request(parsed)

    def validate(self, request: object) -> ValidatedM1901Request:
        """Validate a request and issue an instance-scoped execution capability."""

        validated = self._engine.validate_request(request)
        token = ValidatedM1901Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(self, request: object | ValidatedM1901Request) -> ProteotypeUpstreamResolutionResult:
        if type(request) is ValidatedM1901Request:
            if request._seal is not self._seal or not _token_is_issued(request, self._seal):
                raise M1901TokenError
            return self._engine.resolve(request.request)
        return self._engine.resolve(request)

    def replay(
        self, result: ProteotypeUpstreamResolutionResult
    ) -> ProteotypeUpstreamResolutionResult:
        return self._engine.replay(result)


__all__ = [
    "M1901Plugin",
    "M1901PluginDescriptor",
    "M1901TokenError",
    "ValidatedM1901Request",
]
