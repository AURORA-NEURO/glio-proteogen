"""Parse-once plugin boundary for M18-08."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_08 import (
    BiomarkerPanelTranslationMonitoringResult,
    MonitorBiomarkerPanelTranslationHealthRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .service import M1808Service

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorBiomarkerPanelTranslationHealthRequest)


class ValidatedM1808Request:
    """Opaque token coupling one validated request to this plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: MonitorBiomarkerPanelTranslationHealthRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1808Request,
        tuple[object, MonitorBiomarkerPanelTranslationHealthRequest, bytes],
    ]
] = WeakKeyDictionary()


class M1808TokenError(TypeError):
    """A plugin token was forged, mutated, or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M18-08 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M1808PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-08"
    operation: str = "monitor_biomarker_panel_translation_health"
    output_media_type: str = "application/vnd.glio-proteogen.m18-08+json"
    parent_target: str = "biomarker panel"
    owner: str = "Scientific engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G5"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    unsupported_to_negative: bool = False
    explicit_abstention: bool = True


class M1808Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M1808PluginDescriptor()

    def __init__(self, service: M1808Service | None = None) -> None:
        self._service = service or M1808Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM1808Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM1808Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def validate_request(self, request: object) -> MonitorBiomarkerPanelTranslationHealthRequest:
        """Validate a request without exposing the opaque execution token."""

        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def run(self, token: ValidatedM1808Request) -> BiomarkerPanelTranslationMonitoringResult:
        if not isinstance(token, ValidatedM1808Request):
            raise M1808TokenError
        snapshot = _TOKENS.get(token)
        if snapshot is None or snapshot[0] is not self._seal or token._seal is not self._seal:
            raise M1808TokenError
        if snapshot[1] is not token.request:
            raise M1808TokenError
        try:
            current_bytes = canonical_json_bytes(token.request)
        except (TypeError, ValueError) as error:
            raise M1808TokenError from error
        if current_bytes != snapshot[2]:
            raise M1808TokenError
        return self._service._engine.infer(snapshot[1])

    def verify(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        return self._service.verify(result)

    def replay(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        return self.verify(result)


__all__ = [
    "M1808Plugin",
    "M1808PluginDescriptor",
    "M1808TokenError",
    "ValidatedM1808Request",
]
