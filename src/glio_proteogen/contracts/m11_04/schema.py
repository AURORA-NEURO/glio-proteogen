"""JSON Schema 2020-12 exports for provisional M11-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_04.v1 import (
    M1104_CONTRACT_VERSION,
    M1104_GATE,
    M1104_M1101_RESULT_MEDIA_TYPE,
    M1104_MAX_CANONICAL_REQUEST_BYTES,
    M1104_MODULE_ID,
    M1104_OUTPUT_MEDIA_TYPE,
    M1104_OWNER,
    M1104_PARENT,
    M1104_PROVISIONAL_ABI,
    M1104_SAFETY_CLASS,
    InferVariantPeptideMechanismRequest,
    MechanismEstimate,
    MechanismFinding,
    MechanismInferenceConfiguration,
    VariantPeptideMechanismInferenceResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M11-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M1104_CONTRACT_VERSION
ContractName = Literal["request", "output", "estimate", "configuration", "finding"]
_CONTRACTS: Final = {
    "request": InferVariantPeptideMechanismRequest,
    "output": VariantPeptideMechanismInferenceResult,
    "estimate": MechanismEstimate,
    "configuration": MechanismInferenceConfiguration,
    "finding": MechanismFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M11-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1104_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1104_OWNER,
        "safetyClass": M1104_SAFETY_CLASS,
        "gate": M1104_GATE,
        "strict": True,
        "provisionalAbi": M1104_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1104_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1104_OUTPUT_MEDIA_TYPE,
        "hypothesisInputMediaType": M1104_M1101_RESULT_MEDIA_TYPE,
        "counterEvidenceRequired": True,
        "assumptionsAndAlternativesRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1104_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M11-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
