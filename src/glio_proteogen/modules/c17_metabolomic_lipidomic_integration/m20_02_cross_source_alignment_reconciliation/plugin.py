"""Sealed strict M20-02 plugin descriptor and parse-once boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M2002Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m20_02 import (
        AlignProteinSubtypeSourcesRequest,
        ProteinSubtypeAlignmentResult,
    )


@dataclass(frozen=True, slots=True)
class M2002PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M20-02"
    operation: str = "align_protein_subtype_sources"
    output_media_type: str = "application/vnd.glio-proteogen.m20-02+json"
    upstream_media_type: str = "application/vnd.glio-proteogen.m20-01+json"
    parent_target: str = "protein subtype"
    owner: str = "Quality engineering"
    safety_class: str = "S2"
    gate: str = "G1"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_discovery: bool = True
    explicit_abstention: bool = True


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM2002Request:
    """Opaque capability proving strict M20-02 request validation."""

    request: AlignProteinSubtypeSourcesRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM2002Request,
        tuple[object, AlignProteinSubtypeSourcesRequest, bytes],
    ]
] = WeakKeyDictionary()


def _canonical_request_bytes(request: AlignProteinSubtypeSourcesRequest) -> bytes:
    return canonical_json_bytes(request.model_dump(mode="json"))


def _token_is_issued(token: ValidatedM2002Request, seal: object) -> bool:
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


class M2002TokenError(TypeError):
    """A plugin execution token was forged or belongs to another plugin."""

    def __init__(self) -> None:
        super().__init__("M20-02 requires a token produced by this plugin")


class M2002Plugin:
    """Expose strict request validation, reconciliation, and exact replay."""

    __slots__ = ("_engine", "_seal")

    descriptor: Final = M2002PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M2002Engine()
        self._seal = object()

    def validate_request(self, candidate: object) -> AlignProteinSubtypeSourcesRequest:
        return self._engine.validate_request(candidate)

    def validate(self, candidate: object) -> ValidatedM2002Request:
        """Validate a request and issue an instance-scoped execution capability."""

        validated = self._engine.validate_request(candidate)
        token = ValidatedM2002Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, _canonical_request_bytes(validated))
        return token

    def run(
        self,
        request: AlignProteinSubtypeSourcesRequest | ValidatedM2002Request,
    ) -> ProteinSubtypeAlignmentResult:
        if type(request) is ValidatedM2002Request:
            if request._seal is not self._seal or not _token_is_issued(request, self._seal):
                raise M2002TokenError
            return self._engine.resolve(request.request)
        return self._engine.resolve(request)

    def verify(self, result: ProteinSubtypeAlignmentResult) -> ProteinSubtypeAlignmentResult:
        return self._engine.replay(result)


__all__ = [
    "M2002Plugin",
    "M2002PluginDescriptor",
    "M2002TokenError",
    "ValidatedM2002Request",
]
