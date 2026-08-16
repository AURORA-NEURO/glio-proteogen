"""Strict JSON plugin boundary for M19-01."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from .engine import M1901Engine

_MAX_JSON_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class M1901PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M19-01"
    operation: str = "resolve_proteotype_upstream_contracts"
    output_media_type: str = "application/vnd.glio-proteogen.m19-01+json"
    parent_target: str = "proteotype"
    owner: str = "Bioinformatics"
    safety_class: str = "S2"
    gate: str = "G0"
    provisional_abi: bool = True
    external_content_traversal: bool = False
    all_omics_fusion: bool = False
    kinase_activity: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    upstream_mutation: bool = False
    disagreement_erasure: bool = False
    unsupported_to_negative: bool = False
    typed_discovery: bool = True
    typed_rejections: bool = True
    explicit_abstention: bool = True


class M1901Plugin:
    """Expose only strict request resolution and exact replay."""

    def __init__(self) -> None:
        self._engine = M1901Engine()

    @property
    def descriptor(self) -> M1901PluginDescriptor:
        return M1901PluginDescriptor()

    def validate_json(self, payload: str | bytes) -> Any:
        raw = payload.encode() if isinstance(payload, str) else payload
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("M19-01 request exceeds canonical size limit")
        try:
            document = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("M19-01 request must be valid JSON") from exc
        return self._engine.validate_request(document)

    def run(self, request: object) -> Any:
        return self._engine.resolve(request)

    def replay(self, result: Any) -> Any:
        return self._engine.replay(result)


__all__ = ["M1901Plugin", "M1901PluginDescriptor"]
