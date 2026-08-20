"""Strict service seam for M26-04 publication and replay."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_04 import (
    M2604_MAX_CANONICAL_REQUEST_BYTES,
    M2604_MAX_CANONICAL_RESULT_BYTES,
    ProteinSubtypeAccessSurfaceResult,
    PublishProteinSubtypeAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2604GatewayEngine, preflight_m2604_authorization

_REQUEST_ADAPTER = TypeAdapter(PublishProteinSubtypeAccessSurfaceRequest)


def _bounded_mapping_json(mapping: Mapping[object, object], *, max_bytes: int, label: str) -> bytes:
    encoded = canonical_json_bytes(dict(mapping))
    if len(encoded) > max_bytes:
        raise ValueError(f"{label} exceeds canonical byte limit")  # noqa: TRY003
    return encoded


class M2604Service:
    """Validate, publish, and replay through one deterministic gateway engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2604GatewayEngine | None = None) -> None:
        self._engine = engine or M2604GatewayEngine()

    def validate_request(self, request: object) -> PublishProteinSubtypeAccessSurfaceRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2604_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2604_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2604_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(
                _bounded_mapping_json(
                    request,
                    max_bytes=M2604_MAX_CANONICAL_REQUEST_BYTES,
                    label="M26-04 request",
                ),
                strict=True,
            )
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def publish(self, request: object) -> ProteinSubtypeAccessSurfaceResult:
        return self._engine.publish(self.validate_request(request))

    def replay(self, result: object) -> ProteinSubtypeAccessSurfaceResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2604_MAX_CANONICAL_RESULT_BYTES)
            typed = ProteinSubtypeAccessSurfaceResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif isinstance(result, Mapping):
            typed = ProteinSubtypeAccessSurfaceResult.model_validate_json(
                _bounded_mapping_json(
                    result,
                    max_bytes=M2604_MAX_CANONICAL_RESULT_BYTES,
                    label="M26-04 result",
                ),
                strict=True,
            )
        else:
            typed = ProteinSubtypeAccessSurfaceResult.model_validate(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M26-04",
            "operation": "publish_protein_subtype_access_surface",
            "owner": "Quality engineering",
            "safety_class": "S3",
            "gate": "G2",
            "parent": "protein subtype",
            "provisional_abi": True,
            "typed_operations": True,
            "authorization": True,
            "idempotency": True,
            "asynchronous_jobs": True,
            "compatibility": True,
            "signed_release_bundle_fallback": True,
            "unsupported_to_negative": False,
            "prohibited_outputs": (
                "protein subtype claim",
                "kinase activity",
                "generic all-omics fusion",
                "treatment recommendation",
                "identity inference",
                "consent inference",
            ),
        }


__all__ = ["M2604Service"]
