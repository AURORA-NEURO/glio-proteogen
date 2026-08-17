"""JSON Schema 2020-12 exports for provisional M27-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_05.v1 import (
    M2605_CONTRACT_VERSION,
    M2605_GATE,
    M2605_M2604_INPUT_MEDIA_TYPE,
    M2605_MAX_CANONICAL_REQUEST_BYTES,
    M2605_MODULE_ID,
    M2605_OUTPUT_MEDIA_TYPE,
    M2605_OWNER,
    M2605_PARENT,
    M2605_PROVISIONAL_ABI,
    M2605_SAFETY_CLASS,
    AlertRecord,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    ReviewerActionRecord,
    SafeFailureReport,
    TelemetrySample,
    TelemetryStream,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M2605_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "stream",
    "sample",
    "dashboard",
    "alert",
    "reviewer-action",
    "safe-failure",
]
_CONTRACTS: Final = {
    "request": EmitProteomicsTelemetryRequest,
    "output": ProteomicsTelemetryResult,
    "stream": TelemetryStream,
    "sample": TelemetrySample,
    "dashboard": DashboardDefinition,
    "alert": AlertRecord,
    "reviewer-action": ReviewerActionRecord,
    "safe-failure": SafeFailureReport,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2605_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2605_OWNER,
        "safetyClass": M2605_SAFETY_CLASS,
        "gate": M2605_GATE,
        "strict": True,
        "provisionalAbi": M2605_PROVISIONAL_ABI,
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
        "parentTarget": M2605_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2605_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2605_M2604_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration_bayesian_nonparametric_subtype",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries_open_set_proteotype",
        "fallbackArchitecture": "offline_signed_release_bundles_latent_class_proteotype",
        "inputQualityRequired": True,
        "identityValidationRequired": True,
        "versionValidationRequired": True,
        "unitValidationRequired": True,
        "completenessValidationRequired": True,
        "assaySupportValidationRequired": True,
        "parentQualityValidationRequired": True,
        "quarantineUnresolvedInputs": True,
        "modelBehaviorRequired": True,
        "uncertaintyRequired": True,
        "uncertaintyDimensions": (
            "measurement",
            "sampling",
            "parameter",
            "model_form",
            "identification",
            "support",
            "transport",
        ),
        "abstentionRequired": True,
        "driftRequired": True,
        "latencyRequired": True,
        "errorsRequired": True,
        "resourcesRequired": True,
        "reviewerActionsRequired": True,
        "telemetryRetentionRequired": True,
        "dashboardsRequired": True,
        "alertStateRequired": True,
        "criticalSignalsRetained": True,
        "alertDrillEvidenceRequired": True,
        "humanReviewCriticalDiscrepancy": True,
        "humanReviewNovelOodState": True,
        "humanReviewSupportOverride": True,
        "humanReviewClaimPromotion": True,
        "humanReviewReleaseException": True,
        "humanReviewBiologicalConflict": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2605_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M27-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
