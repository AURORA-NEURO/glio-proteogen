"""JSON Schema 2020-12 exports for provisional M25-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_07.v1 import (
    M2507_CONTRACT_VERSION,
    M2507_GATE,
    M2507_M2506_INPUT_MEDIA_TYPE,
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    M2507_MODULE_ID,
    M2507_OUTPUT_MEDIA_TYPE,
    M2507_OWNER,
    M2507_PARENT,
    M2507_PROVISIONAL_ABI,
    M2507_SAFETY_CLASS,
    EvaluateProteotypeHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalFinding,
    OperationalMetric,
    ProteotypeHumanFactorsResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M25-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2507_CONTRACT_VERSION
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
    "request": EvaluateProteotypeHumanFactorsRequest,
    "output": ProteotypeHumanFactorsResult,
    "report": HumanFactorsOperationalReport,
    "metric": OperationalMetric,
    "fallback": FallbackScenario,
    "configuration": OperationalConfiguration,
    "finding": OperationalFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M25-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2507_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2507_OWNER,
        "safetyClass": M2507_SAFETY_CLASS,
        "gate": M2507_GATE,
        "strict": True,
        "provisionalAbi": M2507_PROVISIONAL_ABI,
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
        "parentTarget": M2507_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2507_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2507_M2506_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "longitudinal_state_space",
        "alternateArchitecture": "longitudinal_state_space",
        "fallbackArchitecture": "spatial_proteotype_field",
        "spatialProteotypeField": True,
        "reviewerComprehensionRequired": True,
        "automationBiasAssessmentRequired": True,
        "throughputLatencyRequired": True,
        "downtimeRecoveryRequired": True,
        "fallbackRequired": True,
        "userInterpretationRequired": True,
        "operationalObjectivesRequired": True,
        "uncertaintyRequired": True,
        "humanReviewRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2507_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M25-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
