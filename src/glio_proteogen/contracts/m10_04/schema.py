"""JSON Schema 2020-12 exports for provisional M10-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_04.v1 import (
    M1004_BASELINE_MEDIA_TYPE,
    M1004_CONTRACT_VERSION,
    M1004_GATE,
    M1004_MAX_CANONICAL_REQUEST_BYTES,
    M1004_MODULE_ID,
    M1004_OUTPUT_MEDIA_TYPE,
    M1004_OWNER,
    M1004_PARENT,
    M1004_PROVISIONAL_ABI,
    M1004_SAFETY_CLASS,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    EstimatorConstraint,
    OptimizationDiagnostic,
    PosteriorEstimate,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticPrior,
    ProteinRnaDiscordanceProbabilisticResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1004_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "posterior",
    "diagnostic",
    "prior",
    "constraint",
    "configuration",
]
_CONTRACTS: Final = {
    "request": EstimateProteinRnaDiscordanceProbabilisticRequest,
    "output": ProteinRnaDiscordanceProbabilisticResult,
    "posterior": PosteriorEstimate,
    "diagnostic": OptimizationDiagnostic,
    "prior": ProbabilisticPrior,
    "constraint": EstimatorConstraint,
    "configuration": ProbabilisticEstimatorConfiguration,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1004_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1004_OWNER,
        "safetyClass": M1004_SAFETY_CLASS,
        "gate": M1004_GATE,
        "strict": True,
        "provisionalAbi": M1004_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1004_PARENT,
        "unsupportedToNegative": False,
        "preregisteredObjectiveRequired": True,
        "deterministicSeedRequired": True,
        "priorsAndConstraintsDeclared": True,
        "optimizationDiagnosticsRequired": True,
        "failureHandlingExplicit": True,
        "outputMediaType": M1004_OUTPUT_MEDIA_TYPE,
        "baselineInputMediaType": M1004_BASELINE_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1004_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
