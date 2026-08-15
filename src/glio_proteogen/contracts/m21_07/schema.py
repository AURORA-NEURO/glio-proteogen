"""JSON Schema 2020-12 exports for provisional M21-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_07.v1 import (
    M2107_CONTRACT_VERSION,
    M2107_GATE,
    M2107_M2106_INPUT_MEDIA_TYPE,
    M2107_MAX_CANONICAL_REQUEST_BYTES,
    M2107_MODULE_ID,
    M2107_OUTPUT_MEDIA_TYPE,
    M2107_OWNER,
    M2107_PARENT,
    M2107_PROVISIONAL_ABI,
    M2107_SAFETY_CLASS,
    ComplexActivityHumanFactorsResult,
    EvaluateComplexActivityHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalFinding,
    OperationalMetric,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2107_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "report",
    "metric",
    "fallback",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": EvaluateComplexActivityHumanFactorsRequest,
    "output": ComplexActivityHumanFactorsResult,
    "report": HumanFactorsOperationalReport,
    "metric": OperationalMetric,
    "fallback": FallbackScenario,
    "configuration": OperationalConfiguration,
    "finding": OperationalFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2107_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2107_OWNER,
        "safetyClass": M2107_SAFETY_CLASS,
        "gate": M2107_GATE,
        "strict": True,
        "provisionalAbi": M2107_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2107_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2107_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2107_M2106_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "recurrence_transition",
        "alternateArchitecture": "clone_linked_protein_evolution",
        "fallbackArchitecture": "spatial_proteotype_field",
        "reviewerComprehensionRequired": True,
        "automationBiasAssessmentRequired": True,
        "throughputLatencyRequired": True,
        "downtimeRecoveryRequired": True,
        "fallbackRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2107_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M21-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
