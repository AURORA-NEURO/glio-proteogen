"""JSON Schema 2020-12 exports for provisional M24-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_04.v1 import (
    M2404_CONTRACT_VERSION,
    M2404_GATE,
    M2404_MAX_CANONICAL_REQUEST_BYTES,
    M2404_MODULE_ID,
    M2404_OUTPUT_MEDIA_TYPE,
    M2404_OWNER,
    M2404_PARENT,
    M2404_PROVISIONAL_ABI,
    M2404_SAFETY_CLASS,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportEvaluation,
    TransportFinding,
    TransportValidation,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M24-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2404_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "validation",
    "evaluation",
    "support-domain-update",
    "configuration",
    "report",
    "finding",
]
_CONTRACTS: Final = {
    "request": EvaluateBiomarkerPanelExternalTransportRequest,
    "output": BiomarkerPanelExternalTransportResult,
    "validation": TransportValidation,
    "evaluation": TransportEvaluation,
    "support-domain-update": SupportDomainUpdate,
    "configuration": TransportConfiguration,
    "report": TransportabilityReport,
    "finding": TransportFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M24-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2404_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2404_OWNER,
        "safetyClass": M2404_SAFETY_CLASS,
        "gate": M2404_GATE,
        "strict": True,
        "provisionalAbi": M2404_PROVISIONAL_ABI,
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
        "parentTarget": M2404_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2404_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "ptmAwareStateModelRequired": True,
        "isoformAwareQuantificationAvailable": True,
        "externalTransportRequired": True,
        "independentSiteLabPlatformValidationRequired": True,
        "treatmentEraPopulationDiseaseClassSpecimenRequired": True,
        "calibrationFloorsRequired": True,
        "supportDomainNarrowingAllowed": True,
        "provenanceRequired": True,
        "uncertaintyRequired": True,
        "humanReviewRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2404_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M24-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
