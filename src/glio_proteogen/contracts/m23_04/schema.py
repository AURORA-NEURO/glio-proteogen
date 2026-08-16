"""JSON Schema 2020-12 exports for provisional M23-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_04.v1 import (
    M2304_CONTRACT_VERSION,
    M2304_DOSSIER_SHA256,
    M2304_DOSSIER_SLICE,
    M2304_GATE,
    M2304_MAX_CANONICAL_REQUEST_BYTES,
    M2304_MODULE_ID,
    M2304_OUTPUT_MEDIA_TYPE,
    M2304_OWNER,
    M2304_PARENT,
    M2304_PROVISIONAL_ABI,
    M2304_SAFETY_CLASS,
    EvaluateVariantPeptideExternalTransportRequest,
    SupportDomainUpdate,
    TransportabilityReport,
    TransportConfiguration,
    TransportEvaluation,
    TransportFinding,
    TransportValidation,
    VariantPeptideExternalTransportResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M23-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2304_CONTRACT_VERSION
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
    "request": EvaluateVariantPeptideExternalTransportRequest,
    "output": VariantPeptideExternalTransportResult,
    "validation": TransportValidation,
    "evaluation": TransportEvaluation,
    "support-domain-update": SupportDomainUpdate,
    "configuration": TransportConfiguration,
    "report": TransportabilityReport,
    "finding": TransportFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M23-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2304_MODULE_ID,
        "dossierSha256": M2304_DOSSIER_SHA256,
        "dossierSlice": M2304_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2304_OWNER,
        "safetyClass": M2304_SAFETY_CLASS,
        "gate": M2304_GATE,
        "strict": True,
        "provisionalAbi": M2304_PROVISIONAL_ABI,
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
        "parentTarget": M2304_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2304_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "distributed_simulation_continuous_challenge",
        "alternateArchitecture": "locked_offline_benchmark_harness",
        "fallbackArchitecture": "independent_dual_run_validation",
        "isoformAwareQuantificationRequired": True,
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2304_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M23-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
