"""JSON Schema 2020-12 exports for provisional M20-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_04.v1 import (
    M2004_CONTRACT_VERSION,
    M2004_GATE,
    M2004_M2003_INPUT_MEDIA_TYPE,
    M2004_MAX_CANONICAL_REQUEST_BYTES,
    M2004_MODULE_ID,
    M2004_OUTPUT_MEDIA_TYPE,
    M2004_OWNER,
    M2004_PARENT,
    M2004_PROVISIONAL_ABI,
    M2004_SAFETY_CLASS,
    AdapterFinding,
    AdaptProteinSubtypeIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseRegistration,
    IntendedUseSpecificObject,
    PolicyDecision,
    ProteinSubtypeIntendedUseAdapterResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M2004_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "registration",
    "claim-ceiling",
    "display-semantics",
    "policy-decision",
    "intended-use-object",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdaptProteinSubtypeIntendedUseRequest,
    "output": ProteinSubtypeIntendedUseAdapterResult,
    "registration": IntendedUseRegistration,
    "claim-ceiling": ClaimCeiling,
    "display-semantics": DisplaySemantics,
    "policy-decision": PolicyDecision,
    "intended-use-object": IntendedUseSpecificObject,
    "finding": AdapterFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2004_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2004_OWNER,
        "safetyClass": M2004_SAFETY_CLASS,
        "gate": M2004_GATE,
        "strict": True,
        "provisionalAbi": M2004_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M2004_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2004_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2004_M2003_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "structure_aware_proteoform_model",
        "alternateArchitecture": "typed_service_integration",
        "fallbackArchitecture": "proteoform_probabilistic_model",
        "intendedUseRegistrationRequired": True,
        "evidenceTierRequired": True,
        "claimCeilingRequired": True,
        "displaySemanticsRequired": True,
        "policyDecisionRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2004_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M20-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
