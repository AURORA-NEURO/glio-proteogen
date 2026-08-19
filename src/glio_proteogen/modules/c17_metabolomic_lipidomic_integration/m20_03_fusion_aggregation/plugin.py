"""Sealed M20-03 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m20_03 import canonical_request_bytes

from .engine import M2003Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_03 import (
        FuseProteinSubtypeEvidenceRequest,
        ProteinSubtypeIntegratedEvidenceResult,
    )


@dataclass(frozen=True, slots=True)
class M2003PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-03"
    operation: str = "fuse_protein_subtype_evidence"
    output_media_type: str = "application/vnd.glio-proteogen.m20-03+json"
    parent_target: str = "protein subtype"
    owner: str = "Clinical science"
    safety_class: str = "S2"
    gate: str = "G2"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    source_attribution: bool = True
    disagreement_preservation: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2003Request:
    """Opaque capability proving strict M20-03 request validation."""

    request: FuseProteinSubtypeEvidenceRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2003Request,
        tuple[object, FuseProteinSubtypeEvidenceRequest, bytes],
    ]
] = WeakKeyDictionary()


def _token_is_issued(token: ValidatedM2003Request, seal: object) -> bool:
    try:
        snapshot = _TOKENS.get(token)
        current = canonical_request_bytes(token.request)
    except (TypeError, ValueError):
        return False
    return (
        snapshot is not None
        and snapshot[0] is seal
        and snapshot[1] is token.request
        and snapshot[2] == current
    )


class M2003TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M20-03 requires a token produced by this plugin")


class M2003Plugin:
    """Expose only typed fusion and exact replay."""

    __slots__ = ("_engine", "_seal")

    descriptor: Final = M2003PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2003Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> FuseProteinSubtypeEvidenceRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM2003Request:
        """Validate a request and issue an instance-scoped execution capability."""

        validated = self._engine.validate_request(candidate)
        token = ValidatedM2003Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: FuseProteinSubtypeEvidenceRequest | ValidatedM2003Request,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        if type(request) is ValidatedM2003Request:
            if request._seal is not self._seal or not _token_is_issued(request, self._seal):
                raise M2003TokenError
            return self._engine.fuse(request.request)
        return self._engine.fuse(request)

    def replay(
        self,
        result: ProteinSubtypeIntegratedEvidenceResult,
    ) -> ProteinSubtypeIntegratedEvidenceResult:
        return self._engine.replay(result)


__all__ = [
    "M2003Plugin",
    "M2003PluginDescriptor",
    "M2003TokenError",
    "ValidatedM2003Request",
]
