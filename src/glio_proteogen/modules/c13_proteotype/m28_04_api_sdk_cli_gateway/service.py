"""Strict service seam for M28-04 publication and replay."""

from __future__ import annotations

from pydantic import TypeAdapter

from glio_proteogen.contracts.m28_04 import (
    M2804_MAX_CANONICAL_REQUEST_BYTES,
    M2804_MAX_CANONICAL_RESULT_BYTES,
    ProteinRnaDiscordanceAccessSurfaceResult,
    PublishProteinRnaDiscordanceAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2804GatewayEngine, preflight_m2804_authorization

_REQUEST_ADAPTER = TypeAdapter(PublishProteinRnaDiscordanceAccessSurfaceRequest)


class M2804Service:
    """Validate, publish, and replay through one deterministic gateway engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2804GatewayEngine | None = None) -> None:
        self._engine = engine or M2804GatewayEngine()

    def validate_request(self, request: object) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2804_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2804_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2804_authorization(request)
        if type(request) is dict:
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        if isinstance(request, PublishProteinRnaDiscordanceAccessSurfaceRequest):
            return _REQUEST_ADAPTER.validate_python(request, strict=True)
        raise TypeError from None

    def publish(self, request: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        return self._engine.publish(self.validate_request(request))

    def replay(self, result: object) -> ProteinRnaDiscordanceAccessSurfaceResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2804_MAX_CANONICAL_RESULT_BYTES)
            typed = ProteinRnaDiscordanceAccessSurfaceResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif type(result) is dict:
            typed = ProteinRnaDiscordanceAccessSurfaceResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        elif isinstance(result, ProteinRnaDiscordanceAccessSurfaceResult):
            typed = ProteinRnaDiscordanceAccessSurfaceResult.model_validate(result, strict=True)
        else:
            raise TypeError from None
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M28-04",
            "operation": "publish_protein_rna_discordance_access_surface",
            "owner": "Data engineering",
            "safety_class": "S3",
            "gate": "G2",
            "parent": "protein-RNA discordance",
            "provisional_abi": True,
            "typed_operations": True,
            "authorization": True,
            "idempotency": True,
            "asynchronous_jobs": True,
            "compatibility": True,
            "signed_release_bundle_fallback": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "protein-RNA discordance claim",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2804Service"]
