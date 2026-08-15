"""JSON Schema 2020-12 exports for provisional M14-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_08.v1 import (
    M1408_CONTRACT_VERSION,
    M1408_GATE,
    M1408_MAX_CANONICAL_REQUEST_BYTES,
    M1408_MODULE_ID,
    M1408_OUTPUT_MEDIA_TYPE,
    M1408_OWNER,
    M1408_PARENT,
    M1408_PROVISIONAL_ABI,
    M1408_SAFETY_CLASS,
    DossierConfiguration,
    DossierFinding,
    EvidenceLink,
    MechanismClaim,
    MechanismEvidenceDossier,
    ProteinSubtypeMechanismEvidenceDossierResult,
    PublishProteinSubtypeMechanismDossierRequest,
    ValidationRoute,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-08:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1408_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "evidence-link",
    "claim",
    "validation-route",
    "dossier",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": PublishProteinSubtypeMechanismDossierRequest,
    "output": ProteinSubtypeMechanismEvidenceDossierResult,
    "evidence-link": EvidenceLink,
    "claim": MechanismClaim,
    "validation-route": ValidationRoute,
    "dossier": MechanismEvidenceDossier,
    "configuration": DossierConfiguration,
    "finding": DossierFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1408_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1408_OWNER,
        "safetyClass": M1408_SAFETY_CLASS,
        "gate": M1408_GATE,
        "strict": True,
        "provisionalAbi": M1408_PROVISIONAL_ABI,
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
        "parentTarget": M1408_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1408_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_bayesian_model_averaging",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "reconstructableEvidenceChainRequired": True,
        "counterEvidenceRequired": True,
        "validationRouteRequired": True,
        "claimCeilingRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1408_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M14-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
