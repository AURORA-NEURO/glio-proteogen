"""Opaque parse-once plugin boundary for provisional M22-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_04 import (
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    ProteinRnaDiscordanceExternalTransportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .service import M2204Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateProteinRnaDiscordanceExternalTransportRequest)


class ValidatedM2204Request:
    """Opaque, instance-bound token for one validated request snapshot."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: EvaluateProteinRnaDiscordanceExternalTransportRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2204Request,
        tuple[object, EvaluateProteinRnaDiscordanceExternalTransportRequest, bytes],
    ]
] = WeakKeyDictionary()


class M2204TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M22-04 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2204PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M22-04"
    operation: str = "evaluate_protein_rna_discordance_external_transport"
    output_media_type: str = "application/vnd.glio-proteogen.m22-04+json"
    upstream_media_types: tuple[str, str] = (
        "application/vnd.glio-proteogen.m22-02+json",
        "application/vnd.glio-proteogen.m22-03+json",
    )
    parent_target: str = "protein-RNA discordance"
    owner: str = "Scientific engineering"
    safety_class: str = "S3"
    evidence_gate: str = "G3"
    provisional_abi: bool = True
    external_transport: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2204Plugin:
    """Strict plugin with non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2204PluginDescriptor()

    def __init__(self, service: M2204Service | None = None) -> None:
        self._service = service or M2204Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM2204Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2204Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def validate_request(
        self, request: object
    ) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def run(self, token: ValidatedM2204Request) -> ProteinRnaDiscordanceExternalTransportResult:
        if not isinstance(token, ValidatedM2204Request):
            raise M2204TokenError
        snapshot = _TOKENS.get(token)
        if (
            snapshot is None
            or snapshot[0] is not self._seal
            or token._seal is not self._seal
            or snapshot[1] is not token.request
            or snapshot[2] != canonical_json_bytes(token.request)
        ):
            raise M2204TokenError
        return self._service._engine.evaluate(snapshot[1])

    def replay(self, result: object) -> ProteinRnaDiscordanceExternalTransportResult:
        return self._service.replay(result)


__all__ = [
    "M2204Plugin",
    "M2204PluginDescriptor",
    "M2204TokenError",
    "ValidatedM2204Request",
]
