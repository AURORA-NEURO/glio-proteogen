"""Sealed M18-06 plugin descriptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from weakref import WeakKeyDictionary

from glio_proteogen.contracts.m18_06 import AdjudicateBiomarkerPanelQueueRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes

from .engine import M1806Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m18_06 import (
        BiomarkerPanelAdjudicationResult,
    )


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class ValidatedM1806Request:
    """Opaque, instance-bound capability for one validated request snapshot."""

    request: AdjudicateBiomarkerPanelQueueRequest
    _seal: object


_TOKENS: Final[
    WeakKeyDictionary[
        ValidatedM1806Request, tuple[object, AdjudicateBiomarkerPanelQueueRequest, bytes]
    ]
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class M1806PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M18-06"
    operation: str = "adjudicate_biomarker_panel_discrepancy_queue"
    output_media_type: str = "application/vnd.glio-proteogen.m18-06+json"
    parent_target: str = "biomarker panel"
    owner: str = "Data engineering"
    safety_class: str = "S2"
    evidence_gate: str = "G4"
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
    blinded_review: bool = True
    immutable_history: bool = True
    explicit_abstention: bool = True


class M1806Plugin:
    """Expose only bounded adjudication and exact replay."""

    descriptor: Final = M1806PluginDescriptor()

    def __init__(self) -> None:
        self._engine = M1806Engine()
        self._seal = object()
        self._validated: dict[int, tuple[AdjudicateBiomarkerPanelQueueRequest, bytes]] = {}

    def validate_request(self, candidate: object) -> AdjudicateBiomarkerPanelQueueRequest:
        validated = self._engine.validate_request(candidate)
        self._validated[id(validated)] = (validated, canonical_json_bytes(validated))
        return validated

    def validate(self, candidate: object) -> ValidatedM1806Request:
        """Issue an instance-bound capability while retaining ``validate_request`` ABI."""

        validated = self.validate_request(candidate)
        token = ValidatedM1806Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_json_bytes(validated))
        return token

    def run(
        self,
        request: object,
    ) -> BiomarkerPanelAdjudicationResult:
        if type(request) is ValidatedM1806Request:
            snapshot = _TOKENS.get(request)
            if (
                snapshot is None
                or snapshot[0] is not self._seal
                or request._seal is not self._seal
                or snapshot[1] is not request.request
                or snapshot[2] != canonical_json_bytes(request.request)
            ):
                raise TypeError("M18-06 execution requires a validated request token")  # noqa: TRY003
            return self._engine.adapt(snapshot[1])
        if isinstance(request, AdjudicateBiomarkerPanelQueueRequest):
            record = self._validated.get(id(request))
            if record is None or record[0] is not request:
                validated = self.validate_request(request)
                record = (validated, canonical_json_bytes(validated))
            if record[1] != canonical_json_bytes(request):
                raise TypeError("M18-06 execution requires an unchanged validated request")  # noqa: TRY003
            return self._engine.adapt(record[0])
        validated = self.validate_request(request)
        return self._engine.adapt(validated)

    def replay(
        self,
        result: BiomarkerPanelAdjudicationResult,
    ) -> BiomarkerPanelAdjudicationResult:
        return self._engine.replay(result)


__all__ = ["M1806Plugin", "M1806PluginDescriptor", "ValidatedM1806Request"]
