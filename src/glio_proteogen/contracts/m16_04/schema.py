"""JSON Schema 2020-12 exports for provisional M16-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_04.v1 import (
    M1604_CONTRACT_VERSION,
    M1604_GATE,
    M1604_MAX_CANONICAL_REQUEST_BYTES,
    M1604_MODULE_ID,
    M1604_OUTPUT_MEDIA_TYPE,
    M1604_OWNER,
    M1604_PARENT,
    M1604_PROVISIONAL_ABI,
    M1604_SAFETY_CLASS,
    AdapterConfiguration,
    AdaptProteinRnaDiscordanceIntendedUseRequest,
    IntendedUseFinding,
    IntendedUseObject,
    IntendedUsePolicy,
    PolicyDecision,
    ProteinRnaDiscordanceIntendedUseResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M1604_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "intended-use-object",
    "policy-decision",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdaptProteinRnaDiscordanceIntendedUseRequest,
    "output": ProteinRnaDiscordanceIntendedUseResult,
    "policy": IntendedUsePolicy,
    "intended-use-object": IntendedUseObject,
    "policy-decision": PolicyDecision,
    "configuration": AdapterConfiguration,
    "finding": IntendedUseFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1604_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1604_OWNER,
        "safetyClass": M1604_SAFETY_CLASS,
        "gate": M1604_GATE,
        "strict": True,
        "provisionalAbi": M1604_PROVISIONAL_ABI,
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
        "parentTarget": M1604_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1604_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m16-01+json",
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration_variant_peptide_graph",
        "fallbackArchitecture": "signed_human_review_package_proteoform_probabilistic_model",
        "registeredIntendedUseRequired": True,
        "audienceRequired": True,
        "evidenceTierRequired": True,
        "claimCeilingRequired": True,
        "displaySemanticsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1604_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M16-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
