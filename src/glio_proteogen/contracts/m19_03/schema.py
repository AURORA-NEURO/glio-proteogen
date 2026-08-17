"""JSON Schema 2020-12 exports for provisional M19-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_03.v1 import (
    M1903_CONTRACT_VERSION,
    M1903_DOSSIER_SHA256,
    M1903_DOSSIER_SLICE,
    M1903_GATE,
    M1903_M1902_INPUT_MEDIA_TYPE,
    M1903_MAX_CANONICAL_REQUEST_BYTES,
    M1903_MODULE_ID,
    M1903_OUTPUT_MEDIA_TYPE,
    M1903_OWNER,
    M1903_PARENT,
    M1903_PROVISIONAL_ABI,
    M1903_SAFETY_CLASS,
    AggregationConfiguration,
    DisagreementRecord,
    FuseProteotypeEvidenceRequest,
    FusionFinding,
    IntegratedEvidenceObject,
    ProteotypeIntegratedEvidenceResult,
    SourceContribution,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M1903_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "integrated-evidence",
    "source-contribution",
    "disagreement",
    "aggregation",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": FuseProteotypeEvidenceRequest,
    "output": ProteotypeIntegratedEvidenceResult,
    "integrated-evidence": IntegratedEvidenceObject,
    "source-contribution": SourceContribution,
    "disagreement": DisagreementRecord,
    "aggregation": AggregationConfiguration,
    "configuration": AggregationConfiguration,
    "finding": FusionFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1903_MODULE_ID,
        "dossierSha256": M1903_DOSSIER_SHA256,
        "dossierSlice": M1903_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1903_OWNER,
        "safetyClass": M1903_SAFETY_CLASS,
        "gate": M1903_GATE,
        "strict": True,
        "provisionalAbi": M1903_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "ownershipPreserved": True,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1903_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1903_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1903_M1902_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "event_driven_reliability_aware_orchestration_stoichiometric_factorization"
        ),
        "alternateArchitecture": "typed_service_oriented_integration_pathway_activity_network",
        "fallbackArchitecture": "signed_human_review_package_protein_complex_graph",
        "componentSpecificIntegration": True,
        "sourceAttributionRequired": True,
        "reliabilityRequired": True,
        "uncertaintyRequired": True,
        "disagreementPreservationRequired": True,
        "humanReviewRequiredForConflict": True,
        "explicitAbstentionRequired": True,
        "humanReviewRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1903_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all public provisional M19-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
