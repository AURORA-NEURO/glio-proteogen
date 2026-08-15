"""JSON Schema 2020-12 exports for provisional M06-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_04.v1 import (
    M0604_CONTRACT_VERSION,
    M0604_GATE,
    M0604_MAX_CANONICAL_REQUEST_BYTES,
    M0604_MODULE_ID,
    M0604_OUTPUT_MEDIA_TYPE,
    M0604_OWNER,
    M0604_PARENT,
    M0604_PROVISIONAL_ABI,
    M0604_SAFETY_CLASS,
    EstimateProteinAbundanceProbabilisticRequest,
    EstimateProteinAbundanceProbabilisticResult,
    EstimatorConstraint,
    OptimizationDiagnostic,
    PosteriorEstimate,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticPrior,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M0604_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "prior",
    "constraint",
    "posterior",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": EstimateProteinAbundanceProbabilisticRequest,
    "output": EstimateProteinAbundanceProbabilisticResult,
    "configuration": ProbabilisticEstimatorConfiguration,
    "prior": ProbabilisticPrior,
    "constraint": EstimatorConstraint,
    "posterior": PosteriorEstimate,
    "diagnostic": OptimizationDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema; this inventory is not frozen ABI."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0604_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0604_OWNER,
        "safetyClass": M0604_SAFETY_CLASS,
        "gate": M0604_GATE,
        "strict": True,
        "provisionalAbi": M0604_PROVISIONAL_ABI,
        "pendingOwnerConfirmation": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "provisionalLimits": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "posteriorOutput": True,
        "calibrationFrozen": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "kinaseActivityInference": False,
        "parentTarget": M0604_PARENT,
        "outputMediaType": M0604_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0604_MAX_CANONICAL_REQUEST_BYTES
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
