"""Strict plugin seam for M19-04 intended-use adaptation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m19_04 import AdaptProteotypeIntendedUseRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1904Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_04 import ProteotypeIntendedUseAdapterResult


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1904Request:
    """Opaque, instance-bound capability for one validated request snapshot."""

    request: AdaptProteotypeIntendedUseRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1904Request, tuple[object, AdaptProteotypeIntendedUseRequest, bytes]
    ]
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class M1904PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-04"
    operation: str = "adapt_proteotype_intended_use"
    output_media_type: str = "application/vnd.glio-proteogen.m19-04+json"
    parent_target: str = "proteotype"
    owner: str = "Clinical science"
    safety_class: str = "S2"
    gate: str = "G3"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    intended_use_registration: bool = True
    explicit_abstention: bool = True


class M1904Plugin:
    """Expose only strict validate, run and replay operations."""

    descriptor: Final = M1904PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1904Engine()
        self._seal = object()
        self._validated: dict[int, tuple[AdaptProteotypeIntendedUseRequest, bytes]] = {}

    def validate_request(self, candidate: object) -> AdaptProteotypeIntendedUseRequest:
        validated = self._engine.validate_request(candidate)
        self._validated[id(validated)] = (validated, canonical_json_bytes(validated))
        return validated

    def validate(self, candidate: object) -> ValidatedM1904Request:
        """Issue an instance-bound capability while retaining ``validate_request`` ABI."""

        validated = self.validate_request(candidate)
        token = ValidatedM1904Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def run(
        self,
        request: object,
    ) -> ProteotypeIntendedUseAdapterResult:
        if type(request) is ValidatedM1904Request:
            snapshot = _TOKENS.get(request)
            if (
                snapshot is None
                or snapshot[0] is not self._seal
                or request._seal is not self._seal
                or snapshot[1] is not request.request
                or snapshot[2] != canonical_json_bytes(request.request)
            ):
                raise TypeError("M19-04 execution requires a validated request token")  # noqa: TRY003
            return self._engine.adapt(snapshot[1])
        if isinstance(request, AdaptProteotypeIntendedUseRequest):
            record = self._validated.get(id(request))
            if record is None or record[0] is not request:
                validated = self.validate_request(request)
                record = (validated, canonical_json_bytes(validated))
            if record[1] != canonical_json_bytes(request):
                raise TypeError("M19-04 execution requires an unchanged validated request")  # noqa: TRY003
            return self._engine.adapt(record[0])
        validated = self.validate_request(request)
        return self._engine.adapt(validated)

    def replay(
        self,
        result: ProteotypeIntendedUseAdapterResult,
    ) -> ProteotypeIntendedUseAdapterResult:
        return self._engine.replay(result)


__all__ = ["M1904Plugin", "M1904PluginDescriptor", "ValidatedM1904Request"]
