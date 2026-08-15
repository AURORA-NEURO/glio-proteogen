"""JSON Schema 2020-12 exports for provisional M05-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_07.v1 import (
    M0507_CONTRACT_VERSION,
    M0507_GATE,
    M0507_MAX_CANONICAL_REQUEST_BYTES,
    M0507_MODULE_ID,
    M0507_OUTPUT_MEDIA_TYPE,
    M0507_OWNER,
    M0507_PARENT,
    M0507_SAFETY_CLASS,
    PtmLocalizationSupportFact,
    PtmLocalizationSupportPolicy,
    PtmLocalizationSupportPrerequisites,
    PtmLocalizationSupportReceipt,
    PtmLocalizationSupportRouteResult,
    RoutePtmLocalizationSupportRequest,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0507_CONTRACT_VERSION
ContractName = Literal["request", "output", "policy", "prerequisites", "fact", "receipt"]
_CONTRACTS: Final = {
    "request": RoutePtmLocalizationSupportRequest,
    "output": PtmLocalizationSupportRouteResult,
    "policy": PtmLocalizationSupportPolicy,
    "prerequisites": PtmLocalizationSupportPrerequisites,
    "fact": PtmLocalizationSupportFact,
    "receipt": PtmLocalizationSupportReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M05-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0507_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0507_OWNER,
        "safetyClass": M0507_SAFETY_CLASS,
        "gate": M0507_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "variantPeptideEmission": False,
        "parentTarget": M0507_PARENT,
        "outputMediaType": M0507_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0507_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M05-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
