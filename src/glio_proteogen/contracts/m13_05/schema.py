"""JSON Schema 2020-12 exports for provisional M13-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_05.v1 import (
    M1305_CONTRACT_VERSION,
    M1305_GATE,
    M1305_M1304_RESULT_MEDIA_TYPE,
    M1305_MAX_CANONICAL_REQUEST_BYTES,
    M1305_MODULE_ID,
    M1305_OUTPUT_MEDIA_TYPE,
    M1305_OWNER,
    M1305_PARENT,
    M1305_PROVISIONAL_ABI,
    M1305_SAFETY_CLASS,
    ChangePoint,
    EvolutionModelConfiguration,
    LongitudinalDiagnostic,
    ModelProteotypeLongitudinalEvolutionRequest,
    ProteotypeLongitudinalEvolutionResult,
    TimePointObservation,
    TrajectoryPolicy,
    TrajectoryState,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M13-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M1305_CONTRACT_VERSION
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
    "request": ModelProteotypeLongitudinalEvolutionRequest,
    "output": ProteotypeLongitudinalEvolutionResult,
    "observation": TimePointObservation,
    "trajectory-state": TrajectoryState,
    "change-point": ChangePoint,
    "configuration": EvolutionModelConfiguration,
    "policy": TrajectoryPolicy,
    "diagnostic": LongitudinalDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M13-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1305_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1305_OWNER,
        "safetyClass": M1305_SAFETY_CLASS,
        "gate": M1305_GATE,
        "strict": True,
        "provisionalAbi": M1305_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "parentTarget": M1305_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1305_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1305_M1304_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "semi_supervised_classifier",
        "alternateArchitecture": "mixture_of_experts_subtype",
        "fallbackArchitecture": "latent_class_proteotype",
        "temporalOrderingRequired": True,
        "futureLeakageBlocked": True,
        "changePointsExplicit": True,
        "trajectoryEvidenceRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "reproductionWithinTolerance": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1305_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M13-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
