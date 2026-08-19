"""Strict, parse-once plugin boundary for M19-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_08 import MonitorProteotypeTranslationHealthRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1908TranslationMonitoringEngine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_08 import ProteotypeTranslationMonitoringResult

_REQUEST_ADAPTER: TypeAdapter[MonitorProteotypeTranslationHealthRequest] = TypeAdapter(
    MonitorProteotypeTranslationHealthRequest
)
_MAX_JSON_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class M1908PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-08"
    operation: str = "monitor_proteotype_translation_health"
    output_media_type: str = "application/vnd.glio-proteogen.m19-08+json"
    parent_target: str = "proteotype"
    owner: str = "Computational biology"
    safety_class: str = "S2"
    gate: str = "G5"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    generic_all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    usage_telemetry: bool = True
    support_drift: bool = True
    workflow_effects: bool = True
    discrepancies: bool = True
    suspension_and_rollback: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1908Request:
    """Opaque capability proving strict M19-08 request validation."""

    request: MonitorProteotypeTranslationHealthRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1908Request,
        tuple[object, MonitorProteotypeTranslationHealthRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: MonitorProteotypeTranslationHealthRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM1908Request, seal: object) -> bool:
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


class M1908TokenError(ValueError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M19-08 requires a token produced by this plugin")


class M1908Plugin:
    """Expose strict JSON validation, execution, and exact replay."""

    def __init__(self) -> None:
        self._engine = M1908TranslationMonitoringEngine()
        self._seal = object()

    @property
    def descriptor(self) -> M1908PluginDescriptor:
        return M1908PluginDescriptor()

    def validate_request(self, request: object) -> MonitorProteotypeTranslationHealthRequest:
        return self._engine.validate_request(request)

    def validate(self, request: object) -> ValidatedM1908Request:
        """Validate a typed request and return an instance-bound execution token."""

        validated = self._engine.validate_request(request)
        token = ValidatedM1908Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def validate_json(self, payload: str | bytes) -> ValidatedM1908Request:
        raw = payload.encode() if isinstance(payload, str) else payload
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("M19-08 request exceeds canonical size limit")  # noqa: TRY003
        try:
            document = strict_json_loads(raw, max_bytes=_MAX_JSON_BYTES)
        except StrictJsonError as exc:
            raise ValueError("M19-08 request must be valid JSON") from exc  # noqa: TRY003
        parsed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(document), strict=True)
        validated = self._engine.validate_request(parsed)
        token = ValidatedM1908Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(self, request: object) -> ProteotypeTranslationMonitoringResult:
        if (
            type(request) is not ValidatedM1908Request
            or request._seal is not self._seal
            or not _token_is_issued(request, self._seal)
        ):
            raise M1908TokenError
        return self._engine.infer(request.request)

    def verify(self, result: object) -> ProteotypeTranslationMonitoringResult:
        return self._engine.verify(result)

    def replay(self, result: object) -> ProteotypeTranslationMonitoringResult:
        return self._engine.replay(result)


__all__ = [
    "M1908Plugin",
    "M1908PluginDescriptor",
    "M1908TokenError",
    "ValidatedM1908Request",
]
