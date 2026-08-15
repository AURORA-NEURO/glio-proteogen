"""JSON Schema 2020-12 exports for provisional M07-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_04.v1 import (
    M0704_CONTRACT_VERSION,
    M0704_GATE,
    M0704_MAX_CANONICAL_REQUEST_BYTES,
    M0704_MODULE_ID,
    M0704_OUTPUT_MEDIA_TYPE,
    M0704_OWNER,
    M0704_PARENT,
    M0704_PROVISIONAL_ABI,
    M0704_REPRESENTATION_MEDIA_TYPE,
    M0704_SAFETY_CLASS,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimateCopyNumberDosageProbabilisticResult,
    EstimatorConstraint,
    OptimizationDiagnostic,
    PosteriorEstimate,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticPrior,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0704_CONTRACT_VERSION
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
    "request": EstimateCopyNumberDosageProbabilisticRequest,
    "output": EstimateCopyNumberDosageProbabilisticResult,
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
        "moduleId": M0704_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0704_OWNER,
        "safetyClass": M0704_SAFETY_CLASS,
        "gate": M0704_GATE,
        "strict": True,
        "provisionalAbi": M0704_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "provisionalLimits": True,
        "modelMetricsFrozen": False,
        "externalContentTraversal": False,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "kinaseActivityInference": False,
        "parentTarget": M0704_PARENT,
        "outputMediaType": M0704_OUTPUT_MEDIA_TYPE,
        "representationInputMediaType": M0704_REPRESENTATION_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0704_MAX_CANONICAL_REQUEST_BYTES
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
