"""JSON Schema 2020-12 exports for provisional M21-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_04.v1 import (
    M2104_CONTRACT_VERSION,
    M2104_DOSSIER_SHA256,
    M2104_DOSSIER_SLICE,
    M2104_GATE,
    M2104_M2103_INPUT_MEDIA_TYPE,
    M2104_MAX_CANONICAL_REQUEST_BYTES,
    M2104_MODULE_ID,
    M2104_OUTPUT_MEDIA_TYPE,
    M2104_OWNER,
    M2104_PARENT,
    M2104_PROVISIONAL_ABI,
    M2104_SAFETY_CLASS,
    ComplexActivityExternalTransportResult,
    EvaluateComplexActivityExternalTransportRequest,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportEvaluation,
    TransportFinding,
    TransportValidation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-04:0.1.0-provisional"
CONTRACT_VERSION: Final = M2104_CONTRACT_VERSION
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
    "request": EvaluateComplexActivityExternalTransportRequest,
    "output": ComplexActivityExternalTransportResult,
    "validation": TransportValidation,
    "evaluation": TransportEvaluation,
    "support-domain-update": SupportDomainUpdate,
    "configuration": TransportConfiguration,
    "report": TransportabilityReport,
    "finding": TransportFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2104_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2104_OWNER,
        "safetyClass": M2104_SAFETY_CLASS,
        "gate": M2104_GATE,
        "strict": True,
        "provisionalAbi": M2104_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "dossierSha256": M2104_DOSSIER_SHA256,
        "dossierSlice": M2104_DOSSIER_SLICE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M2104_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2104_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2104_M2103_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "externalTransportRequired": True,
        "independentSiteLabPlatformValidationRequired": True,
        "treatmentEraPopulationDiseaseClassSpecimenRequired": True,
        "calibrationFloorsRequired": True,
        "supportDomainNarrowingAllowed": True,
        "provenanceRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2104_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M21-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
