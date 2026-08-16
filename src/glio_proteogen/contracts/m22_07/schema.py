"""JSON Schema 2020-12 exports for provisional M22-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_07.v1 import (
    M2207_CONTRACT_VERSION,
    M2207_DOSSIER_SHA256,
    M2207_DOSSIER_SLICE,
    M2207_GATE,
    M2207_M2206_INPUT_MEDIA_TYPE,
    M2207_MAX_CANONICAL_REQUEST_BYTES,
    M2207_MODULE_ID,
    M2207_OUTPUT_MEDIA_TYPE,
    M2207_OWNER,
    M2207_PARENT,
    M2207_PROVISIONAL_ABI,
    M2207_SAFETY_CLASS,
    EvaluateProteinRnaDiscordanceHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalFinding,
    OperationalMetric,
    ProteinRnaDiscordanceHumanFactorsResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2207_CONTRACT_VERSION
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
    "request": EvaluateProteinRnaDiscordanceHumanFactorsRequest,
    "output": ProteinRnaDiscordanceHumanFactorsResult,
    "report": HumanFactorsOperationalReport,
    "metric": OperationalMetric,
    "fallback": FallbackScenario,
    "configuration": OperationalConfiguration,
    "finding": OperationalFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2207_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2207_OWNER,
        "safetyClass": M2207_SAFETY_CLASS,
        "gate": M2207_GATE,
        "strict": True,
        "provisionalAbi": M2207_PROVISIONAL_ABI,
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
        "parentTarget": M2207_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2207_OUTPUT_MEDIA_TYPE,
        "inputMediaType": M2207_M2206_INPUT_MEDIA_TYPE,
        "dossierSha256": M2207_DOSSIER_SHA256,
        "dossierSlice": M2207_DOSSIER_SLICE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "cloneLinkedProteinEvolution": True,
        "territoryConditionedSubtype": True,
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2207_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M22-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
