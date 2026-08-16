"""Strict service seam for M23-04 transport evaluation and replay."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m23_04 import (
    M2304_MAX_CANONICAL_REQUEST_BYTES,
    M2304_MAX_CANONICAL_RESULT_BYTES,
    EvaluateVariantPeptideExternalTransportRequest,
    VariantPeptideExternalTransportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2304Engine


class M2304Service:
    """Parse once, evaluate deterministically, and verify exact replay."""

    def __init__(self, engine: M2304Engine | None = None) -> None:
        self._engine = engine or M2304Engine()

    def validate_request(self, request: object) -> EvaluateVariantPeptideExternalTransportRequest:
        return EvaluateVariantPeptideExternalTransportRequest.model_validate(request, strict=True)

    def evaluate(self, request: object) -> VariantPeptideExternalTransportResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=M2304_MAX_CANONICAL_REQUEST_BYTES)
            request = EvaluateVariantPeptideExternalTransportRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = EvaluateVariantPeptideExternalTransportRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.evaluate(request)

    def verify_replay(self, result: object) -> VariantPeptideExternalTransportResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=M2304_MAX_CANONICAL_RESULT_BYTES)
            result = VariantPeptideExternalTransportResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = VariantPeptideExternalTransportResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            result = VariantPeptideExternalTransportResult.model_validate(result, strict=True)
        return self._engine.replay(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M23-04",
            "operation": "evaluate_variant_peptide_external_transport",
            "owner": "Computational biology",
            "safety_class": "S3",
            "gate": "G3",
            "parent": "variant peptide",
            "provisional_abi": True,
            "external_transport": True,
            "independent_site_lab_platform_validation": True,
            "isoform_aware_quantification": True,
            "calibration_floors": True,
            "support_domain_narrowing": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2304Service"]
