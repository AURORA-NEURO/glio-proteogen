"""Strict service seam for M23-08 adjudication and replay."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_08 import (
    M2308_MAX_CANONICAL_REQUEST_BYTES,
    M2308_MAX_CANONICAL_RESULT_BYTES,
    AdjudicateVariantPeptideEvidenceGateRequest,
    VariantPeptideEvidenceGateResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2308EvidenceGateEngine, preflight_m2308_authorization

_REQUEST_ADAPTER = TypeAdapter(AdjudicateVariantPeptideEvidenceGateRequest)


class M2308Service:
    """Validate, adjudicate, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2308EvidenceGateEngine | None = None) -> None:
        self._engine = engine or M2308EvidenceGateEngine()

    def validate_request(
        self, request: object
    ) -> AdjudicateVariantPeptideEvidenceGateRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2308_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2308_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2308_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def adjudicate(self, request: object) -> VariantPeptideEvidenceGateResult:
        return self._engine.adjudicate(self.validate_request(request))

    def replay(self, result: object) -> VariantPeptideEvidenceGateResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2308_MAX_CANONICAL_RESULT_BYTES)
            typed = VariantPeptideEvidenceGateResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif isinstance(result, Mapping):
            typed = VariantPeptideEvidenceGateResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            typed = VariantPeptideEvidenceGateResult.model_validate(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M23-08",
            "operation": "adjudicate_variant_peptide_evidence_gate",
            "owner": "Clinical science",
            "safety_class": "S3",
            "gate": "G5",
            "parent": "variant peptide",
            "provisional_abi": True,
            "traceability": True,
            "risk_controls": True,
            "claim_ceiling": True,
            "signed_release_record": True,
            "post_release_obligations": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "variant-peptide estimate",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2308Service"]
