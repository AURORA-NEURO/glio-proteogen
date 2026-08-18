"""JSON Schema 2020-12 exports for provisional M19-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_08.v1 import (
    M1908_CONTRACT_VERSION,
    M1908_GATE,
    M1908_M1907_INPUT_MEDIA_TYPE,
    M1908_MAX_CANONICAL_REQUEST_BYTES,
    M1908_MODULE_ID,
    M1908_OUTPUT_MEDIA_TYPE,
    M1908_OWNER,
    M1908_PARENT,
    M1908_PROHIBITED_CLAIM_TERMS,
    M1908_PROVISIONAL_ABI,
    M1908_SAFETY_CLASS,
    DiscrepancyObservation,
    MonitorProteotypeTranslationHealthRequest,
    ProteotypeTranslationMonitoringResult,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationFinding,
    TranslationHealthReport,
    WorkflowEffectObservation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1908_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "health-report",
    "telemetry",
    "support-drift",
    "workflow-effect",
    "discrepancy",
    "rollback-policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": MonitorProteotypeTranslationHealthRequest,
    "output": ProteotypeTranslationMonitoringResult,
    "health-report": TranslationHealthReport,
    "telemetry": TelemetryObservation,
    "support-drift": SupportDriftObservation,
    "workflow-effect": WorkflowEffectObservation,
    "discrepancy": DiscrepancyObservation,
    "rollback-policy": RollbackPolicy,
    "finding": TranslationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1908_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1908_OWNER,
        "safetyClass": M1908_SAFETY_CLASS,
        "gate": M1908_GATE,
        "strict": True,
        "provisionalAbi": M1908_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "mutationInference": False,
        "clinicalClaims": False,
        "prohibitedClaimTerms": list(M1908_PROHIBITED_CLAIM_TERMS),
        "disagreementErasure": False,
        "parentTarget": M1908_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1908_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1908_M1907_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "network_factor_hybrid",
        "alternateArchitecture": "bayesian_model_averaging",
        "fallbackArchitecture": "baseline_stack",
        "usageTelemetryRequired": True,
        "supportDriftRequired": True,
        "workflowEffectsRequired": True,
        "discrepanciesRequired": True,
        "suspensionRollbackRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1908_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M19-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
