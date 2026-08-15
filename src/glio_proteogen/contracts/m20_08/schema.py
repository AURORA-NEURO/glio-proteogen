"""JSON Schema 2020-12 exports for provisional M20-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_08.v1 import (
    M2008_CONTRACT_VERSION,
    M2008_GATE,
    M2008_M2007_INPUT_MEDIA_TYPE,
    M2008_MAX_CANONICAL_REQUEST_BYTES,
    M2008_MODULE_ID,
    M2008_OUTPUT_MEDIA_TYPE,
    M2008_OWNER,
    M2008_PARENT,
    M2008_PROVISIONAL_ABI,
    M2008_SAFETY_CLASS,
    DriftAssessment,
    HealthSignal,
    MonitorDiagnostic,
    MonitorProteinSubtypeTranslationHealthRequest,
    ProteinSubtypeTranslationHealthResult,
    RollbackPlan,
    TranslationHealthReport,
    TranslationMonitoringConfiguration,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-08:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2008_CONTRACT_VERSION
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
    "request": MonitorProteinSubtypeTranslationHealthRequest,
    "output": ProteinSubtypeTranslationHealthResult,
    "report": TranslationHealthReport,
    "signal": HealthSignal,
    "assessment": DriftAssessment,
    "rollback-plan": RollbackPlan,
    "configuration": TranslationMonitoringConfiguration,
    "diagnostic": MonitorDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2008_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2008_OWNER,
        "safetyClass": M2008_SAFETY_CLASS,
        "gate": M2008_GATE,
        "strict": True,
        "provisionalAbi": M2008_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2008_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2008_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2008_M2007_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration_conformal_proteotype",
        "alternateArchitecture": "typed_service_integration_conformal_proteotype",
        "fallbackArchitecture": "human_in_the_loop_signed_review_package_baseline_stack",
        "usageTelemetryRequired": True,
        "supportDriftRequired": True,
        "workflowEffectsRequired": True,
        "discrepancyMonitoringRequired": True,
        "suspensionAndRollbackExplicit": True,
        "rollbackRecoveryRequired": True,
        "uncertaintyRequired": True,
        "provenanceRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2008_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M20-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
