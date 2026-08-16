"""JSON Schema 2020-12 exports for provisional M17-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_08.v1 import (
    M1708_CONTRACT_VERSION,
    M1708_GATE,
    M1708_M1707_INPUT_MEDIA_TYPE,
    M1708_MAX_CANONICAL_REQUEST_BYTES,
    M1708_MODULE_ID,
    M1708_OUTPUT_MEDIA_TYPE,
    M1708_OWNER,
    M1708_PARENT,
    M1708_PROVISIONAL_ABI,
    M1708_SAFETY_CLASS,
    DiscrepancyObservation,
    MonitorVariantPeptideTranslationHealthRequest,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationFinding,
    TranslationHealthReport,
    VariantPeptideTranslationMonitoringResult,
    WorkflowEffectObservation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1708_CONTRACT_VERSION
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
    "request": MonitorVariantPeptideTranslationHealthRequest,
    "output": VariantPeptideTranslationMonitoringResult,
    "health-report": TranslationHealthReport,
    "telemetry": TelemetryObservation,
    "support-drift": SupportDriftObservation,
    "workflow-effect": WorkflowEffectObservation,
    "discrepancy": DiscrepancyObservation,
    "rollback-policy": RollbackPolicy,
    "finding": TranslationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1708_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1708_OWNER,
        "safetyClass": M1708_SAFETY_CLASS,
        "gate": M1708_GATE,
        "strict": True,
        "provisionalAbi": M1708_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1708_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1708_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1708_M1707_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "baseline_stack",
        "alternateArchitecture": "network_factor_hybrid",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1708_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M17-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
