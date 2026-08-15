"""JSON Schema 2020-12 exports for provisional M15-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_06.v1 import (
    M1506_CONTRACT_VERSION,
    M1506_GATE,
    M1506_MAX_CANONICAL_REQUEST_BYTES,
    M1506_MODULE_ID,
    M1506_OUTPUT_MEDIA_TYPE,
    M1506_OWNER,
    M1506_PARENT,
    M1506_PROVISIONAL_ABI,
    M1506_SAFETY_CLASS,
    ComplexActivitySensitivitySimulationResult,
    PerturbationSpecification,
    SensitivityDiagnostic,
    SensitivityResponse,
    SensitivitySimulationConfiguration,
    SensitivitySurface,
    SimulateComplexActivityPerturbationsRequest,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-06:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1506_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "surface",
    "perturbation",
    "response",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": SimulateComplexActivityPerturbationsRequest,
    "output": ComplexActivitySensitivitySimulationResult,
    "surface": SensitivitySurface,
    "perturbation": PerturbationSpecification,
    "response": SensitivityResponse,
    "configuration": SensitivitySimulationConfiguration,
    "diagnostic": SensitivityDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1506_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1506_OWNER,
        "safetyClass": M1506_SAFETY_CLASS,
        "gate": M1506_GATE,
        "strict": True,
        "provisionalAbi": M1506_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1506_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1506_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m15-05+json",
        "boundedResponsesRequired": True,
        "assumptionsRequired": True,
        "negativeControlGatingExplicit": True,
        "alternativePriorsExplicit": True,
        "stressTestsExplicit": True,
        "safeAbstentionRequired": True,
        "primaryArchitecture": "proteogenomic_vae",
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1506_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M15-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
