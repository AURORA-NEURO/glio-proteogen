"""Strict service seam for provisional M21-04 transport evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m21_04 import (
    ComplexActivityExternalTransportResult,
    EvaluateComplexActivityExternalTransportRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2104Engine


class M2104Service:
    """Parse once, evaluate deterministically, and replay exact results."""

    def __init__(self, engine: M2104Engine | None = None) -> None:
        self._engine = engine or M2104Engine()

    def validate_request(self, request: object) -> EvaluateComplexActivityExternalTransportRequest:
        return EvaluateComplexActivityExternalTransportRequest.model_validate(request, strict=True)

    def evaluate(self, request: object) -> ComplexActivityExternalTransportResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=8 * 1024 * 1024)
            request = EvaluateComplexActivityExternalTransportRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = EvaluateComplexActivityExternalTransportRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.evaluate(request)

    def replay(self, result: object) -> ComplexActivityExternalTransportResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=16 * 1024 * 1024)
            result = ComplexActivityExternalTransportResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = ComplexActivityExternalTransportResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            result = ComplexActivityExternalTransportResult.model_validate(result, strict=True)
        return self._engine.replay(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M21-04",
            "operation": "evaluate_complex_activity_external_transport",
            "owner": "Platform engineering",
            "safety_class": "S3",
            "gate": "G3",
            "parent": "complex activity",
            "upstream_media_type": "application/vnd.glio-proteogen.m21-03+json",
            "provisional_abi": True,
            "external_transport": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "complex-activity estimate",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2104Service"]
