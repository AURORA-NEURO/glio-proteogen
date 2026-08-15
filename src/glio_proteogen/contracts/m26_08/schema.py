"""JSON Schema 2020-12 exports for provisional M26-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_08.v1 import (
    M2608_CONTRACT_VERSION,
    M2608_GATE,
    M2608_MAX_CANONICAL_REQUEST_BYTES,
    M2608_MODULE_ID,
    M2608_OUTPUT_MEDIA_TYPE,
    M2608_OWNER,
    M2608_PARENT,
    M2608_PROVISIONAL_ABI,
    M2608_SAFETY_CLASS,
    CommunicationRecord,
    DependencyMigration,
    EvidencePreservation,
    LongTermArchive,
    ProteinSubtypeRetirementResult,
    RetirementConfiguration,
    RetirementCriterion,
    RetirementFinding,
    RetirementPackage,
    RetireProteinSubtypeServiceRequest,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-08:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2608_CONTRACT_VERSION
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
    "request": RetireProteinSubtypeServiceRequest,
    "output": ProteinSubtypeRetirementResult,
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
    """Return one strict, metadata-only provisional M26-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2608_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2608_OWNER,
        "safetyClass": M2608_SAFETY_CLASS,
        "gate": M2608_GATE,
        "strict": True,
        "provisionalAbi": M2608_PROVISIONAL_ABI,
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
        "parentTarget": M2608_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2608_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2608_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M26-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
