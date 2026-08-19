"""Opaque parse-once plugin boundary for provisional M21-07."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .service import M2107Service

if TYPE_CHECKING:
    from glio_proteogen.contracts.m21_07 import (
        ComplexActivityHumanFactorsResult,
        EvaluateComplexActivityHumanFactorsRequest,
    )

_TOKENS: WeakKeyDictionary[
    ValidatedM2107Request,
    tuple[object, EvaluateComplexActivityHumanFactorsRequest, bytes],
] = WeakKeyDictionary()


class ValidatedM2107Request:
    """Opaque token coupling one validated request to one plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(self, request: EvaluateComplexActivityHumanFactorsRequest, seal: object) -> None:
        self.request = request
        self._seal = seal


def _canonical_request_bytes(request: EvaluateComplexActivityHumanFactorsRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2107Request, seal: object) -> bool:
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
        validated = self._service.validate_request(request)
        token = ValidatedM2107Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def validate_request(self, request: object) -> EvaluateComplexActivityHumanFactorsRequest:
        return self._service.validate_request(request)

    def run(self, token: ValidatedM2107Request) -> ComplexActivityHumanFactorsResult:
        if (
            type(token) is not ValidatedM2107Request
            or token._seal is not self._seal
            or not _token_is_issued(token, self._seal)
        ):
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
