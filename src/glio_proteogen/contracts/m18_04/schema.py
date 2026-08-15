"""JSON Schema 2020-12 exports for provisional M18-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_04.v1 import (
    M1804_CONTRACT_VERSION,
    M1804_GATE,
    M1804_M1803_INPUT_MEDIA_TYPE,
    M1804_MAX_CANONICAL_REQUEST_BYTES,
    M1804_MODULE_ID,
    M1804_OUTPUT_MEDIA_TYPE,
    M1804_OWNER,
    M1804_PARENT,
    M1804_PROVISIONAL_ABI,
    M1804_SAFETY_CLASS,
    AdaptBiomarkerPanelIntendedUseRequest,
    AdapterFinding,
    BiomarkerPanelIntendedUseAdapterResult,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseRegistration,
    IntendedUseSpecificObject,
    PolicyDecision,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1804_CONTRACT_VERSION
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
    "request": AdaptBiomarkerPanelIntendedUseRequest,
    "output": BiomarkerPanelIntendedUseAdapterResult,
    "registration": IntendedUseRegistration,
    "claim-ceiling": ClaimCeiling,
    "display-semantics": DisplaySemantics,
    "policy-decision": PolicyDecision,
    "intended-use-object": IntendedUseSpecificObject,
    "finding": AdapterFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1804_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1804_OWNER,
        "safetyClass": M1804_SAFETY_CLASS,
        "gate": M1804_GATE,
        "strict": True,
        "provisionalAbi": M1804_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1804_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1804_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1804_M1803_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "isoform_aware_quantification",
        "alternateArchitecture": "proteoform_probabilistic_model",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1804_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M18-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
