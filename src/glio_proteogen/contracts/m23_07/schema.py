"""JSON Schema 2020-12 exports for provisional M23-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_07.v1 import (
    M2307_CONTRACT_VERSION,
    M2307_GATE,
    M2307_M2306_INPUT_MEDIA_TYPE,
    M2307_MAX_CANONICAL_REQUEST_BYTES,
    M2307_MODULE_ID,
    M2307_OUTPUT_MEDIA_TYPE,
    M2307_OWNER,
    M2307_PARENT,
    M2307_PROVISIONAL_ABI,
    M2307_SAFETY_CLASS,
    EvaluateVariantPeptideHumanFactorsRequest,
    FallbackScenario,
    HumanFactorsOperationalReport,
    OperationalConfiguration,
    OperationalFinding,
    OperationalMetric,
    VariantPeptideHumanFactorsResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M23-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M2307_CONTRACT_VERSION
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
    "request": EvaluateVariantPeptideHumanFactorsRequest,
    "output": VariantPeptideHumanFactorsResult,
    "report": HumanFactorsOperationalReport,
    "metric": OperationalMetric,
    "fallback": FallbackScenario,
    "configuration": OperationalConfiguration,
    "finding": OperationalFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M23-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2307_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2307_OWNER,
        "safetyClass": M2307_SAFETY_CLASS,
        "gate": M2307_GATE,
        "strict": True,
        "provisionalAbi": M2307_PROVISIONAL_ABI,
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
        "parentTarget": M2307_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2307_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2307_M2306_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "spatial_proteotype_field",
        "alternateArchitecture": "recurrence_transition",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2307_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M23-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
