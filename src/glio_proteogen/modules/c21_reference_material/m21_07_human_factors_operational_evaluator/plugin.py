"""Opaque parse-once plugin boundary for provisional M21-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_07 import (
    ComplexActivityHumanFactorsResult,
    EvaluateComplexActivityHumanFactorsRequest,
)

from .service import M2107Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateComplexActivityHumanFactorsRequest)
_TOKENS: WeakKeyDictionary[ValidatedM2107Request, object] = WeakKeyDictionary()


class ValidatedM2107Request:
    """Opaque token coupling one validated request to one plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: EvaluateComplexActivityHumanFactorsRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


class M2107TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M21-07 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2107PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M21-07"
    operation: str = "evaluate_complex_activity_human_factors"
    output_media_type: str = "application/vnd.glio-proteogen.m21-07+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m21-06+json"
    parent_target: str = "complex activity"
    owner: str = "Bioinformatics"
    safety_class: str = "S3"
    evidence_gate: str = "G4"
    provisional_abi: bool = True
    unsupported_to_negative: bool = False
    human_review_required: bool = True
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2107Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2107PluginDescriptor()

    def __init__(self, service: M2107Service | None = None) -> None:
        self._service = service or M2107Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM2107Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2107Request(validated, self._seal)
        _TOKENS[token] = self._seal
        return token

    def validate_request(self, request: object) -> EvaluateComplexActivityHumanFactorsRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def run(self, token: ValidatedM2107Request) -> ComplexActivityHumanFactorsResult:
        if not isinstance(token, ValidatedM2107Request) or _TOKENS.get(token) is not self._seal:
            raise M2107TokenError
        if token._seal is not self._seal:
            raise M2107TokenError
        return self._service._engine.evaluate(token.request)

    def replay(self, result: object) -> ComplexActivityHumanFactorsResult:
        return self._service.replay(result)


__all__ = [
    "M2107Plugin",
    "M2107PluginDescriptor",
    "M2107TokenError",
    "ValidatedM2107Request",
]
