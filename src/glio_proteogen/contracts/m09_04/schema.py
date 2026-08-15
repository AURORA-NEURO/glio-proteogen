"""JSON Schema 2020-12 exports for provisional M09-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_04.v1 import (
    M0904_CONTRACT_VERSION,
    M0904_GATE,
    M0904_MAX_CANONICAL_REQUEST_BYTES,
    M0904_MODULE_ID,
    M0904_OUTPUT_MEDIA_TYPE,
    M0904_OWNER,
    M0904_PARENT,
    M0904_SAFETY_CLASS,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    EstimatorConstraint,
    OptimizationDiagnostic,
    PosteriorEstimate,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticPrior,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M0904_CONTRACT_VERSION
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
    "request": EstimateComplexActivityProbabilisticRequest,
    "output": EstimateComplexActivityProbabilisticResult,
    "posterior": PosteriorEstimate,
    "diagnostic": OptimizationDiagnostic,
    "prior": ProbabilisticPrior,
    "constraint": EstimatorConstraint,
    "configuration": ProbabilisticEstimatorConfiguration,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0904_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0904_OWNER,
        "safetyClass": M0904_SAFETY_CLASS,
        "gate": M0904_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0904_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0904_OUTPUT_MEDIA_TYPE,
        "baselineInputMediaType": "application/vnd.glio-proteogen.m09-03+json",
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0904_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M09-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
