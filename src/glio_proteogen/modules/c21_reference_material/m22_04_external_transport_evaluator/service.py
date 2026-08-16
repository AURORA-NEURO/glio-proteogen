"""Strict service seam for provisional M22-04 transport evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from glio_proteogen.contracts.m22_04 import (
    EvaluateProteinRnaDiscordanceExternalTransportRequest,
    ProteinRnaDiscordanceExternalTransportResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2204Engine


class M2204Service:
    """Parse once, evaluate deterministically, and replay exact results."""

    def __init__(self, engine: M2204Engine | None = None) -> None:
        self._engine = engine or M2204Engine()

    def validate_request(
        self, request: object
    ) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
        return EvaluateProteinRnaDiscordanceExternalTransportRequest.model_validate(
            request, strict=True
        )

    def evaluate(self, request: object) -> ProteinRnaDiscordanceExternalTransportResult:
        if isinstance(request, (bytes, bytearray, str)):
            parsed = strict_json_loads(request, max_bytes=8 * 1024 * 1024)
            request = EvaluateProteinRnaDiscordanceExternalTransportRequest.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(request, Mapping):
            request = EvaluateProteinRnaDiscordanceExternalTransportRequest.model_validate_json(
                canonical_json_bytes(dict(request)), strict=True
            )
        return self._engine.evaluate(request)

    def replay(self, result: object) -> ProteinRnaDiscordanceExternalTransportResult:
        if isinstance(result, (bytes, bytearray, str)):
            parsed = strict_json_loads(result, max_bytes=16 * 1024 * 1024)
            result = ProteinRnaDiscordanceExternalTransportResult.model_validate_json(
                canonical_json_bytes(parsed), strict=True
            )
        elif isinstance(result, Mapping):
            result = ProteinRnaDiscordanceExternalTransportResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            result = ProteinRnaDiscordanceExternalTransportResult.model_validate(
                result, strict=True
            )
        return self._engine.replay(result)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M22-04",
            "operation": "evaluate_protein_rna_discordance_external_transport",
            "owner": "Scientific engineering",
            "safety_class": "S3",
            "gate": "G3",
            "parent": "protein-RNA discordance",
            "upstream_media_types": (
                "application/vnd.glio-proteogen.m22-02+json",
                "application/vnd.glio-proteogen.m22-03+json",
            ),
            "provisional_abi": True,
            "external_transport": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "protein-RNA discordance estimate",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2204Service"]
