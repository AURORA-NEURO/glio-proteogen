"""JSON Schema 2020-12 exports for provisional M25-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_04.v1 import (
    M2504_CONTRACT_VERSION,
    M2504_GATE,
    M2504_MAX_CANONICAL_REQUEST_BYTES,
    M2504_MODULE_ID,
    M2504_OUTPUT_MEDIA_TYPE,
    M2504_OWNER,
    M2504_PARENT,
    M2504_PROVISIONAL_ABI,
    M2504_SAFETY_CLASS,
    EvaluateProteotypeExternalTransportRequest,
    ProteotypeExternalTransportResult,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportEvaluation,
    TransportFinding,
    TransportValidation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M25-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M2504_CONTRACT_VERSION
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
    "request": EvaluateProteotypeExternalTransportRequest,
    "output": ProteotypeExternalTransportResult,
    "validation": TransportValidation,
    "evaluation": TransportEvaluation,
    "support-domain-update": SupportDomainUpdate,
    "configuration": TransportConfiguration,
    "report": TransportabilityReport,
    "finding": TransportFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M25-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2504_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2504_OWNER,
        "safetyClass": M2504_SAFETY_CLASS,
        "gate": M2504_GATE,
        "strict": True,
        "provisionalAbi": M2504_PROVISIONAL_ABI,
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
        "parentTarget": M2504_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2504_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "structureAwareProteoformModelRequired": True,
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2504_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M25-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
