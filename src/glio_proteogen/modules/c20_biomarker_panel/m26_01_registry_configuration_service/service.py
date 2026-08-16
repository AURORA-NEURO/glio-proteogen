"""Strict service seam for M26-01 registry resolution and replay."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_01 import (
    M2601_MAX_CANONICAL_REQUEST_BYTES,
    M2601_MAX_CANONICAL_RESULT_BYTES,
    ProteinSubtypeRegistryResult,
    RegisterProteinSubtypeRegistryRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M2601RegistryEngine, preflight_m2601_authorization

_REQUEST_ADAPTER = TypeAdapter(RegisterProteinSubtypeRegistryRequest)


class M2601Service:
    """Validate, register, and replay through one deterministic engine."""

    __slots__ = ("_engine",)

    def __init__(self, engine: M2601RegistryEngine | None = None) -> None:
        self._engine = engine or M2601RegistryEngine()

    def validate_request(self, request: object) -> RegisterProteinSubtypeRegistryRequest:
        if isinstance(request, (bytes, bytearray, str)):
            decoded = strict_json_loads(request, max_bytes=M2601_MAX_CANONICAL_REQUEST_BYTES)
            preflight_m2601_authorization(decoded)
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        preflight_m2601_authorization(request)
        if isinstance(request, Mapping):
            return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(dict(request)), strict=True)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def register(self, request: object) -> ProteinSubtypeRegistryResult:
        return self._engine.register(self.validate_request(request))

    def replay(self, result: object) -> ProteinSubtypeRegistryResult:
        if isinstance(result, (bytes, bytearray, str)):
            decoded = strict_json_loads(result, max_bytes=M2601_MAX_CANONICAL_RESULT_BYTES)
            typed = ProteinSubtypeRegistryResult.model_validate_json(
                canonical_json_bytes(decoded), strict=True
            )
        elif isinstance(result, Mapping):
            typed = ProteinSubtypeRegistryResult.model_validate_json(
                canonical_json_bytes(dict(result)), strict=True
            )
        else:
            typed = ProteinSubtypeRegistryResult.model_validate(result, strict=True)
        return self._engine.replay(typed)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            "module_id": "GLIO-PROTEOGEN-M26-01",
            "operation": "register_protein_subtype_registry",
            "owner": "Computational biology",
            "safety_class": "S3",
            "gate": "G0",
            "parent": "protein subtype",
            "provisional_abi": True,
            "immutable_history": True,
            "active_configuration": True,
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


__all__ = ["M2601Service"]
