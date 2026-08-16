"""JSON Schema 2020-12 exports for provisional M18-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_08.v1 import (
    M1808_CONTRACT_VERSION,
    M1808_DOSSIER_SHA256,
    M1808_DOSSIER_SLICE,
    M1808_GATE,
    M1808_M1807_INPUT_MEDIA_TYPE,
    M1808_MAX_CANONICAL_REQUEST_BYTES,
    M1808_MODULE_ID,
    M1808_OUTPUT_MEDIA_TYPE,
    M1808_OWNER,
    M1808_PARENT,
    M1808_PROVISIONAL_ABI,
    M1808_SAFETY_CLASS,
    BiomarkerPanelTranslationMonitoringResult,
    DiscrepancyObservation,
    MonitorBiomarkerPanelTranslationHealthRequest,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationFinding,
    TranslationHealthReport,
    WorkflowEffectObservation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1808_CONTRACT_VERSION
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
    "request": MonitorBiomarkerPanelTranslationHealthRequest,
    "output": BiomarkerPanelTranslationMonitoringResult,
    "health-report": TranslationHealthReport,
    "telemetry": TelemetryObservation,
    "support-drift": SupportDriftObservation,
    "workflow-effect": WorkflowEffectObservation,
    "discrepancy": DiscrepancyObservation,
    "rollback-policy": RollbackPolicy,
    "finding": TranslationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1808_MODULE_ID,
        "dossierSha256": M1808_DOSSIER_SHA256,
        "dossierSlice": M1808_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1808_OWNER,
        "safetyClass": M1808_SAFETY_CLASS,
        "gate": M1808_GATE,
        "strict": True,
        "provisionalAbi": M1808_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1808_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1808_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1808_M1807_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_model_averaging",
        "alternateArchitecture": "disagreement_review_ensemble",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1808_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M18-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
