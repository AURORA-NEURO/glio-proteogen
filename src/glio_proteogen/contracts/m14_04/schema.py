"""JSON Schema 2020-12 exports for provisional M14-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_04.v1 import (
    M1404_CONTRACT_VERSION,
    M1404_GATE,
    M1404_M1401_RESULT_MEDIA_TYPE,
    M1404_MAX_CANONICAL_REQUEST_BYTES,
    M1404_MODULE_ID,
    M1404_OUTPUT_MEDIA_TYPE,
    M1404_OWNER,
    M1404_PARENT,
    M1404_PROVISIONAL_ABI,
    M1404_SAFETY_CLASS,
    InferProteinSubtypeMechanismRequest,
    MechanismEstimate,
    MechanismFinding,
    MechanismInferenceConfiguration,
    ProteinSubtypeMechanismInferenceResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M1404_CONTRACT_VERSION
ContractName = Literal["request", "output", "estimate", "configuration", "finding"]
_CONTRACTS: Final = {
    "request": InferProteinSubtypeMechanismRequest,
    "output": ProteinSubtypeMechanismInferenceResult,
    "estimate": MechanismEstimate,
    "configuration": MechanismInferenceConfiguration,
    "finding": MechanismFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1404_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1404_OWNER,
        "safetyClass": M1404_SAFETY_CLASS,
        "gate": M1404_GATE,
        "strict": True,
        "provisionalAbi": M1404_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1404_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1404_OUTPUT_MEDIA_TYPE,
        "hypothesisInputMediaType": M1404_M1401_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "ptm_aware_state_model",
        "alternateArchitecture": "isoform_aware_quantification",
        "fallbackArchitecture": "proteoform_probabilistic_model",
        "counterEvidenceRequired": True,
        "assumptionsAndAlternativesRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1404_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M14-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
