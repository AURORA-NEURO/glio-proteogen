"""JSON Schema 2020-12 exports for provisional M27-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_08.v1 import (
    M2708_CONTRACT_VERSION,
    M2708_GATE,
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    M2708_MODULE_ID,
    M2708_OUTPUT_MEDIA_TYPE,
    M2708_OWNER,
    M2708_PARENT,
    M2708_PROVISIONAL_ABI,
    M2708_SAFETY_CLASS,
    CommunicationRecord,
    ComplexActivityRetirementResult,
    DependencyMigration,
    EvidencePreservation,
    LongTermArchive,
    RetireComplexActivityServiceRequest,
    RetirementConfiguration,
    RetirementCriterion,
    RetirementFinding,
    RetirementPackage,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M2708_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "criterion",
    "migration",
    "evidence",
    "communication",
    "archive",
    "configuration",
    "package",
    "finding",
]
_CONTRACTS: Final = {
    "request": RetireComplexActivityServiceRequest,
    "output": ComplexActivityRetirementResult,
    "criterion": RetirementCriterion,
    "migration": DependencyMigration,
    "evidence": EvidencePreservation,
    "communication": CommunicationRecord,
    "archive": LongTermArchive,
    "configuration": RetirementConfiguration,
    "package": RetirementPackage,
    "finding": RetirementFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2708_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2708_OWNER,
        "safetyClass": M2708_SAFETY_CLASS,
        "gate": M2708_GATE,
        "strict": True,
        "provisionalAbi": M2708_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2708_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2708_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "baselineStackRequired": True,
        "networkFactorHybridFallback": True,
        "retirementCriteriaRequired": True,
        "dependencyMigrationRequired": True,
        "evidencePreservationRequired": True,
        "communicationRequired": True,
        "longTermArchiveRequired": True,
        "retrievableEvidenceRequired": True,
        "noActiveDependencies": True,
        "signedReleaseBundleFallback": True,
        "provenanceRequired": True,
        "uncertaintyRequired": True,
        "humanReviewRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2708_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M27-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
