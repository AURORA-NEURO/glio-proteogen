"""JSON Schema 2020-12 exports for provisional M19-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_04.v1 import (
    M1904_CONTRACT_VERSION,
    M1904_DOSSIER_SHA256,
    M1904_DOSSIER_SLICE,
    M1904_GATE,
    M1904_M1903_INPUT_MEDIA_TYPE,
    M1904_MAX_CANONICAL_REQUEST_BYTES,
    M1904_MODULE_ID,
    M1904_OUTPUT_MEDIA_TYPE,
    M1904_OWNER,
    M1904_PARENT,
    M1904_PROHIBITED_CLAIM_TERMS,
    M1904_PROVISIONAL_ABI,
    M1904_SAFETY_CLASS,
    AdapterFinding,
    AdaptProteotypeIntendedUseRequest,
    ClaimCeiling,
    DisplaySemantics,
    IntendedUseRegistration,
    IntendedUseSpecificObject,
    PolicyDecision,
    ProteotypeIntendedUseAdapterResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M1904_CONTRACT_VERSION
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
    "request": AdaptProteotypeIntendedUseRequest,
    "output": ProteotypeIntendedUseAdapterResult,
    "registration": IntendedUseRegistration,
    "claim-ceiling": ClaimCeiling,
    "display-semantics": DisplaySemantics,
    "policy-decision": PolicyDecision,
    "intended-use-object": IntendedUseSpecificObject,
    "finding": AdapterFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1904_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1904_OWNER,
        "safetyClass": M1904_SAFETY_CLASS,
        "gate": M1904_GATE,
        "strict": True,
        "provisionalAbi": M1904_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "dossierSha256": M1904_DOSSIER_SHA256,
        "dossierSlice": M1904_DOSSIER_SLICE,
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1904_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1904_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1904_M1903_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration",
        "fallbackArchitecture": "human_in_the_loop_signed_review_package",
        "intendedUseRegistrationRequired": True,
        "evidenceTierRequired": True,
        "claimCeilingRequired": True,
        "displaySemanticsRequired": True,
        "policyDecisionRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "kinaseOwnershipInference": False,
        "sourceMutation": False,
        "claimPromotionWithoutReview": False,
        "humanReviewForCriticalDiscrepancy": True,
        "prohibitedClaimTerms": M1904_PROHIBITED_CLAIM_TERMS,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1904_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M19-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
