"""Parse-once plugin boundary for M18-08."""

from __future__ import annotations

from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_08 import (
    BiomarkerPanelTranslationMonitoringResult,
    MonitorBiomarkerPanelTranslationHealthRequest,
)

from .service import M1808Service

_REQUEST_ADAPTER: Final = TypeAdapter(MonitorBiomarkerPanelTranslationHealthRequest)
_TOKENS: WeakKeyDictionary[ValidatedM1808Request, object] = WeakKeyDictionary()


class ValidatedM1808Request:
    """Opaque token coupling one validated request to this plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: MonitorBiomarkerPanelTranslationHealthRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


class M1808TokenError(TypeError):
    """A plugin token was forged, mutated, or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M18-08 requires a validated request token")

class M1808Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")

    def __init__(self, service: M1808Service | None = None) -> None:
        self._service = service or M1808Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM1808Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM1808Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def run(self, token: ValidatedM1808Request) -> BiomarkerPanelTranslationMonitoringResult:
        if not isinstance(token, ValidatedM1808Request) or _TOKENS.get(token) is not self._seal:
            raise M1808TokenError
        if token._seal is not self._seal:
            raise M1808TokenError
        return self._service._engine.infer(token.request)

    def verify(self, result: object) -> BiomarkerPanelTranslationMonitoringResult:
        return self._service.verify(result)


__all__ = ["M1808Plugin", "ValidatedM1808Request"]
