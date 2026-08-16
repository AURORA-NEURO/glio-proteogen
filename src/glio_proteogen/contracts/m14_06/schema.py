"""JSON Schema 2020-12 exports for provisional M14-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_06.v1 import (
    M1406_CONTRACT_VERSION,
    M1406_GATE,
    M1406_MAX_CANONICAL_REQUEST_BYTES,
    M1406_MODULE_ID,
    M1406_OUTPUT_MEDIA_TYPE,
    M1406_OWNER,
    M1406_PARENT,
    M1406_PROVISIONAL_ABI,
    M1406_SAFETY_CLASS,
    PerturbationSpecification,
    ProteinSubtypeSensitivitySimulationResult,
    SensitivityDiagnostic,
    SensitivityResponse,
    SensitivitySimulationConfiguration,
    SensitivitySurface,
    SimulateProteinSubtypePerturbationsRequest,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-06:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1406_CONTRACT_VERSION
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
    "request": SimulateProteinSubtypePerturbationsRequest,
    "output": ProteinSubtypeSensitivitySimulationResult,
    "surface": SensitivitySurface,
    "perturbation": PerturbationSpecification,
    "response": SensitivityResponse,
    "configuration": SensitivitySimulationConfiguration,
    "diagnostic": SensitivityDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1406_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1406_OWNER,
        "safetyClass": M1406_SAFETY_CLASS,
        "gate": M1406_GATE,
        "strict": True,
        "provisionalAbi": M1406_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1406_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1406_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m14-05+json",
        "boundedResponsesRequired": True,
        "assumptionsRequired": True,
        "negativeControlGatingExplicit": True,
        "alternativePriorsExplicit": True,
        "stressTestsExplicit": True,
        "safeAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1406_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M14-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
