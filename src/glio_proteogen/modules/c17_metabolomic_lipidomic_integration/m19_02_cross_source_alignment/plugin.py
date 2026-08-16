"""Strict JSON plugin boundary for M19-02."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_02 import AlignProteotypeSourcesRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1902Engine

if TYPE_CHECKING:
    from glio_proteogen.contracts.m19_02 import ProteotypeAlignmentResult

_REQUEST_ADAPTER: TypeAdapter[AlignProteotypeSourcesRequest] = TypeAdapter(
    AlignProteotypeSourcesRequest
)
_MAX_JSON_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class M1902PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-02"
    operation: str = "align_proteotype_sources"
    output_media_type: str = "application/vnd.glio-proteogen.m19-02+json"
    parent_target: str = "proteotype"
    owner: str = "ML engineering"
    safety_class: str = "S2"
    gate: str = "G1"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    conflict_preservation: bool = True
    explicit_abstention: bool = True


class M1902Plugin:
    """Expose only strict request alignment and exact replay."""

    def __init__(self) -> None:
        self._engine = M1902Engine()

    @property
    def descriptor(self) -> M1902PluginDescriptor:
        return M1902PluginDescriptor()

    def validate_json(self, payload: str | bytes) -> AlignProteotypeSourcesRequest:
        raw = payload.encode() if isinstance(payload, str) else payload
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("M19-02 request exceeds canonical size limit")  # noqa: TRY003
        try:
            document = strict_json_loads(raw, max_bytes=_MAX_JSON_BYTES)
        except StrictJsonError as exc:
            raise ValueError("M19-02 request must be valid JSON") from exc  # noqa: TRY003
        parsed = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(document), strict=True)
        return self._engine.validate_request(parsed)

    def run(self, request: object) -> ProteotypeAlignmentResult:
        return self._engine.align(request)

    def replay(self, result: ProteotypeAlignmentResult) -> ProteotypeAlignmentResult:
        return self._engine.replay(result)


__all__ = ["M1902Plugin", "M1902PluginDescriptor"]
