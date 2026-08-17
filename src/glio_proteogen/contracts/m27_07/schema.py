"""JSON Schema 2020-12 exports for provisional M27-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_07.v1 import (
    M2707_CONTRACT_VERSION,
    M2707_GATE,
    M2707_M2706_INPUT_MEDIA_TYPE,
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    M2707_MODULE_ID,
    M2707_OUTPUT_MEDIA_TYPE,
    M2707_OWNER,
    M2707_PARENT,
    M2707_PROVISIONAL_ABI,
    M2707_SAFETY_CLASS,
    ApprovedChangePackage,
    ChampionChallengerComparison,
    ChangeClassification,
    ComplexActivityChangeControlResult,
    ControlComplexActivityChangeRequest,
    RevalidationPlan,
    RollbackPoint,
    SafeFailureReport,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2707_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "change",
    "revalidation",
    "comparison",
    "package",
    "rollback",
    "safe-failure",
]
_CONTRACTS: Final = {
    "request": ControlComplexActivityChangeRequest,
    "output": ComplexActivityChangeControlResult,
    "change": ChangeClassification,
    "revalidation": RevalidationPlan,
    "comparison": ChampionChallengerComparison,
    "package": ApprovedChangePackage,
    "rollback": RollbackPoint,
    "safe-failure": SafeFailureReport,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2707_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2707_OWNER,
        "safetyClass": M2707_SAFETY_CLASS,
        "gate": M2707_GATE,
        "strict": True,
        "provisionalAbi": M2707_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2707_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2707_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2707_M2706_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration_clone_linked_protein_evolution",
        "alternateArchitecture": "modular_monolith_strict_boundaries_territory_conditioned_subtype",
        "fallbackArchitecture": "offline_signed_release_bundles_spatial_proteotype_field",
        "changeClassificationRequired": True,
        "impactAssessmentRequired": True,
        "revalidationRequired": True,
        "championChallengerRequired": True,
        "approvalRequired": True,
        "stagedRolloutRequired": True,
        "testedRollbackRequired": True,
        "criticalRegressionBlocksPromotion": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2707_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M27-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
