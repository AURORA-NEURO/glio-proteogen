"""JSON Schema 2020-12 exports for provisional M14-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_05.v1 import (
    M1405_CONTRACT_VERSION,
    M1405_GATE,
    M1405_M1404_RESULT_MEDIA_TYPE,
    M1405_MAX_CANONICAL_REQUEST_BYTES,
    M1405_MODULE_ID,
    M1405_OUTPUT_MEDIA_TYPE,
    M1405_OWNER,
    M1405_PARENT,
    M1405_PROVISIONAL_ABI,
    M1405_SAFETY_CLASS,
    ChangePoint,
    EvolutionModelConfiguration,
    LongitudinalDiagnostic,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
    TimePointObservation,
    TrajectoryPolicy,
    TrajectoryState,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-05:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1405_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "observation",
    "trajectory-state",
    "change-point",
    "configuration",
    "policy",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": ModelProteinSubtypeLongitudinalEvolutionRequest,
    "output": ProteinSubtypeLongitudinalEvolutionResult,
    "observation": TimePointObservation,
    "trajectory-state": TrajectoryState,
    "change-point": ChangePoint,
    "configuration": EvolutionModelConfiguration,
    "policy": TrajectoryPolicy,
    "diagnostic": LongitudinalDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1405_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1405_OWNER,
        "safetyClass": M1405_SAFETY_CLASS,
        "gate": M1405_GATE,
        "strict": True,
        "provisionalAbi": M1405_PROVISIONAL_ABI,
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
        "parentTarget": M1405_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1405_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1405_M1404_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_semi_supervised",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "temporalOrderingRequired": True,
        "futureLeakageBlocked": True,
        "changePointsExplicit": True,
        "trajectoryEvidenceRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "reproductionWithinTolerance": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1405_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M14-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
