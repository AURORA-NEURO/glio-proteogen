"""JSON Schema 2020-12 exports for provisional M11-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_02.v1 import (
    M1102_CONTRACT_VERSION,
    M1102_GATE,
    M1102_HYPOTHESIS_MEDIA_TYPE,
    M1102_MAX_CANONICAL_REQUEST_BYTES,
    M1102_MODULE_ID,
    M1102_OUTPUT_MEDIA_TYPE,
    M1102_OWNER,
    M1102_PARENT,
    M1102_PROVISIONAL_ABI,
    M1102_SAFETY_CLASS,
    ContextObservation,
    ContextProfile,
    ContextStratificationPolicy,
    ContextStratificationRule,
    ContextStratifierDiagnostic,
    MechanismApplicability,
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M11-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1102_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "observation",
    "profile",
    "policy",
    "rule",
    "mechanism-applicability",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": StratifyVariantPeptideContextRequest,
    "output": VariantPeptideContextStratificationResult,
    "observation": ContextObservation,
    "profile": ContextProfile,
    "policy": ContextStratificationPolicy,
    "rule": ContextStratificationRule,
    "mechanism-applicability": MechanismApplicability,
    "diagnostic": ContextStratifierDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M11-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1102_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1102_OWNER,
        "safetyClass": M1102_SAFETY_CLASS,
        "gate": M1102_GATE,
        "strict": True,
        "provisionalAbi": M1102_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1102_PARENT,
        "unsupportedToNegative": False,
        "contextDimensionsExplicit": True,
        "mechanismApplicabilityExplicit": True,
        "supportBoundariesRequired": True,
        "prohibitedProxyBlocking": True,
        "uncertaintyRequired": True,
        "outputMediaType": M1102_OUTPUT_MEDIA_TYPE,
        "hypothesisInputMediaType": M1102_HYPOTHESIS_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1102_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
