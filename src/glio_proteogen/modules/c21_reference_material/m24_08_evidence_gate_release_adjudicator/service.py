"""Strict service seam for M24-08 adjudication and replay."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_08 import (
    M2408_MAX_CANONICAL_REQUEST_BYTES,
    M2408_MAX_CANONICAL_RESULT_BYTES,
    AdjudicateBiomarkerPanelEvidenceGateRequest,
    BiomarkerPanelEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2408EvidenceGateEngine, preflight_m2408_authorization

_REQUEST_ADAPTER = TypeAdapter(AdjudicateBiomarkerPanelEvidenceGateRequest)


class M2408Service:
    """Validate, adjudicate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2408EvidenceGateEngine | None = None) -> None:
        self._engine = engine or M2408EvidenceGateEngine()

    def validate_request(self, request: object) -> AdjudicateBiomarkerPanelEvidenceGateRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2408_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2408_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2408_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def adjudicate(self, request: object) -> BiomarkerPanelEvidenceGateResult:
        return self._engine.adjudicate(self.validate_request(request))

    def replay(self, result: object) -> BiomarkerPanelEvidenceGateResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2408_MAX_CANONICAL_RESULT_BYTES)
            typed = BiomarkerPanelEvidenceGateResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif isinstance(result, Mapping):
            typed = BiomarkerPanelEvidenceGateResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            typed = BiomarkerPanelEvidenceGateResult.model_validate(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M24-08",
            "operation": "adjudicate_biomarker_panel_evidence_gate",
            "owner": "Data engineering",
            "safety_class": "S3",
            "gate": "G5",
            "parent": "biomarker panel",
            "provisional_abi": True,
            "traceability": True,
            "risk_controls": True,
            "claim_ceiling": True,
            "signed_release_record": True,
            "post_release_obligations": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "biomarker-panel estimate",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2408Service"]

