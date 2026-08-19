"""Sealed M20-04 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M2004Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_04 import (
        AdaptProteinSubtypeIntendedUseRequest,
        ProteinSubtypeIntendedUseAdapterResult,
    )


@dataclass(frozen=True, slots=True)
class M2004PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-04"
    operation: str = "adapt_protein_subtype_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m20-04+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-03+json"
    parent_target: str = "protein subtype"
    owner: str = "Data engineering"
    safety_class: str = "S2"
    gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    explicit_abstention: bool = True
    claim_ceiling_required: bool = True
    display_semantics_required: bool = True
    evidence_tier_required: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2004Request:
    """Opaque capability proving strict M20-04 request validation."""

    request: AdaptProteinSubtypeIntendedUseRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2004Request,
        tuple[object, AdaptProteinSubtypeIntendedUseRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: AdaptProteinSubtypeIntendedUseRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2004Request, seal: object) -> bool:
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


class _InvalidExecutionTokenError(TypeError):
    def __init__(self) -> None:
        super().__init__("M20-04 execution requires a validated request token")


class M2004Plugin:
    """Expose only typed adaptation and exact replay."""

    descriptor: Final = M2004PluginDescriptor()

    __slots__ = ("_engine", "_seal")

    def __init__(self) -> None:
        self._engine = M2004Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> AdaptProteinSubtypeIntendedUseRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM2004Request:
        """Issue an instance-scoped capability for the exact validated request."""

        validated = self._engine.validate_request(candidate)
        token = ValidatedM2004Request(request=validated, _seal=self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: AdaptProteinSubtypeIntendedUseRequest | ValidatedM2004Request,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        if type(request) is ValidatedM2004Request:
            if request._seal is not self._seal or not _token_is_issued(request, self._seal):
                raise _InvalidExecutionTokenError
            return self._engine.adapt(request.request)
        return self._engine.adapt(request)

    def replay(
        self,
        result: ProteinSubtypeIntendedUseAdapterResult,
    ) -> ProteinSubtypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M2004Plugin", "M2004PluginDescriptor", "ValidatedM2004Request"]
