"""JSON Schema 2020-12 exports for provisional M26-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_07.v1 import (
    M2607_CONTRACT_VERSION,
    M2607_GATE,
    M2607_MAX_CANONICAL_REQUEST_BYTES,
    M2607_MODULE_ID,
    M2607_OUTPUT_MEDIA_TYPE,
    M2607_OWNER,
    M2607_PARENT,
    M2607_PROVISIONAL_ABI,
    M2607_SAFETY_CLASS,
    ChangeFinding,
    ChangePackage,
    ChangeProposal,
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
    RevalidationRecord,
    RollbackPoint,
    ShadowComparison,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2607_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "proposal",
    "revalidation",
    "comparison",
    "rollback",
    "package",
    "finding",
]
_CONTRACTS: Final = {
    "request": ControlProteinSubtypeChangeRequest,
    "output": ProteinSubtypeChangeControlResult,
    "proposal": ChangeProposal,
    "revalidation": RevalidationRecord,
    "comparison": ShadowComparison,
    "rollback": RollbackPoint,
    "package": ChangePackage,
    "finding": ChangeFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M26-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2607_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2607_OWNER,
        "safetyClass": M2607_SAFETY_CLASS,
        "gate": M2607_GATE,
        "strict": True,
        "provisionalAbi": M2607_PROVISIONAL_ABI,
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
        "parentTarget": M2607_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2607_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "primaryMethod": "recurrence_transition",
        "alternateMethod": "clone_linked_protein_evolution",
        "fallbackMethod": "spatial_proteotype_field",
        "changeClassificationRequired": True,
        "revalidationRequired": True,
        "championChallengerRequired": True,
        "stagedRolloutRequired": True,
        "testedRollbackRequired": True,
        "criticalRegressionBlocksPromotion": True,
        "quarantineUnresolvedInputs": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2607_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M26-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
