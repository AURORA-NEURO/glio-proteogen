"""JSON Schema 2020-12 exports for provisional M15-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_04.v1 import (
    M1504_CONTRACT_VERSION,
    M1504_GATE,
    M1504_M1501_RESULT_MEDIA_TYPE,
    M1504_MAX_CANONICAL_REQUEST_BYTES,
    M1504_MODULE_ID,
    M1504_OUTPUT_MEDIA_TYPE,
    M1504_OWNER,
    M1504_PARENT,
    M1504_PROVISIONAL_ABI,
    M1504_SAFETY_CLASS,
    ComplexActivityMechanismInferenceResult,
    InferComplexActivityMechanismRequest,
    MechanismEstimate,
    MechanismFinding,
    MechanismInferenceConfiguration,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1504_CONTRACT_VERSION
ContractName = Literal["request", "output", "estimate", "configuration", "finding"]
_CONTRACTS: Final = {
    "request": InferComplexActivityMechanismRequest,
    "output": ComplexActivityMechanismInferenceResult,
    "estimate": MechanismEstimate,
    "configuration": MechanismInferenceConfiguration,
    "finding": MechanismFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1504_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1504_OWNER,
        "safetyClass": M1504_SAFETY_CLASS,
        "gate": M1504_GATE,
        "strict": True,
        "provisionalAbi": M1504_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1504_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1504_OUTPUT_MEDIA_TYPE,
        "hypothesisInputMediaType": M1504_M1501_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "structure_aware_proteoform_model",
        "alternateArchitecture": "structure_aware_proteoform_model",
        "fallbackArchitecture": "proteoform_probabilistic_model",
        "counterEvidenceRequired": True,
        "assumptionsAndAlternativesRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1504_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M15-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
