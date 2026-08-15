"""JSON Schema 2020-12 exports for provisional M15-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_05.v1 import (
    M1505_CONTRACT_VERSION,
    M1505_DOSSIER_SHA256,
    M1505_DOSSIER_SLICE,
    M1505_GATE,
    M1505_M1504_RESULT_MEDIA_TYPE,
    M1505_MAX_CANONICAL_REQUEST_BYTES,
    M1505_MODULE_ID,
    M1505_OUTPUT_MEDIA_TYPE,
    M1505_OWNER,
    M1505_PARENT,
    M1505_PROVISIONAL_ABI,
    M1505_SAFETY_CLASS,
    ChangePoint,
    ComplexActivityLongitudinalEvolutionResult,
    EvolutionModelConfiguration,
    LongitudinalDiagnostic,
    ModelComplexActivityLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryPolicy,
    TrajectoryState,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M1505_CONTRACT_VERSION
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
    "request": ModelComplexActivityLongitudinalEvolutionRequest,
    "output": ComplexActivityLongitudinalEvolutionResult,
    "observation": TimePointObservation,
    "trajectory-state": TrajectoryState,
    "change-point": ChangePoint,
    "configuration": EvolutionModelConfiguration,
    "policy": TrajectoryPolicy,
    "diagnostic": LongitudinalDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1505_MODULE_ID,
        "dossierSha256": M1505_DOSSIER_SHA256,
        "dossierSlice": M1505_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1505_OWNER,
        "safetyClass": M1505_SAFETY_CLASS,
        "gate": M1505_GATE,
        "strict": True,
        "provisionalAbi": M1505_PROVISIONAL_ABI,
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
        "parentTarget": M1505_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1505_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1505_M1504_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_latent_class_proteotype",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1505_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M15-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
