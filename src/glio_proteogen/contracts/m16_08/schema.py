"""JSON Schema 2020-12 exports for provisional M16-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_08.v1 import (
    M1608_CONTRACT_VERSION,
    M1608_GATE,
    M1608_MAX_CANONICAL_REQUEST_BYTES,
    M1608_MODULE_ID,
    M1608_OUTPUT_MEDIA_TYPE,
    M1608_OWNER,
    M1608_PARENT,
    M1608_PROVISIONAL_ABI,
    M1608_SAFETY_CLASS,
    DriftAssessment,
    HealthSignal,
    MonitorDiagnostic,
    MonitorProteinRnaTranslationHealthRequest,
    ProteinRnaDiscordanceTranslationHealthResult,
    RollbackPlan,
    TranslationHealthReport,
    TranslationMonitoringConfiguration,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1608_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "report",
    "signal",
    "assessment",
    "rollback-plan",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": MonitorProteinRnaTranslationHealthRequest,
    "output": ProteinRnaDiscordanceTranslationHealthResult,
    "report": TranslationHealthReport,
    "signal": HealthSignal,
    "assessment": DriftAssessment,
    "rollback-plan": RollbackPlan,
    "configuration": TranslationMonitoringConfiguration,
    "diagnostic": MonitorDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1608_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1608_OWNER,
        "safetyClass": M1608_SAFETY_CLASS,
        "gate": M1608_GATE,
        "strict": True,
        "provisionalAbi": M1608_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1608_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1608_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m16-07+json",
        "usageTelemetryRequired": True,
        "supportDriftRequired": True,
        "workflowEffectsRequired": True,
        "discrepancyMonitoringRequired": True,
        "suspensionAndRollbackExplicit": True,
        "rollbackRecoveryRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1608_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M16-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
