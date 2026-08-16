"""JSON Schema 2020-12 exports for provisional M12-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_02.v1 import (
    M1202_CONTRACT_VERSION,
    M1202_GATE,
    M1202_MAX_CANONICAL_REQUEST_BYTES,
    M1202_MODULE_ID,
    M1202_OUTPUT_MEDIA_TYPE,
    M1202_OWNER,
    M1202_PARENT,
    M1202_PROVISIONAL_ABI,
    M1202_SAFETY_CLASS,
    ApplicableMechanism,
    BiomarkerPanelContextStratificationResult,
    ContextFinding,
    ContextObservation,
    ContextProfile,
    ContextStratifierConfiguration,
    ContextStratifierPolicy,
    StratifyBiomarkerPanelContextRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M12-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1202_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "observation",
    "profile",
    "mechanism",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": StratifyBiomarkerPanelContextRequest,
    "output": BiomarkerPanelContextStratificationResult,
    "observation": ContextObservation,
    "profile": ContextProfile,
    "mechanism": ApplicableMechanism,
    "configuration": ContextStratifierConfiguration,
    "policy": ContextStratifierPolicy,
    "finding": ContextFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M12-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1202_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1202_OWNER,
        "safetyClass": M1202_SAFETY_CLASS,
        "gate": M1202_GATE,
        "strict": True,
        "provisionalAbi": M1202_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M1202_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1202_OUTPUT_MEDIA_TYPE,
        "contextDimensions": [
            "disease_class",
            "subtype",
            "age",
            "territory",
            "treatment_era",
            "specimen",
            "platform",
            "biological_context",
        ],
        "conflictPreservationRequired": True,
        "quarantineUnresolvedRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1202_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M12-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
