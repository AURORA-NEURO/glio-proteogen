"""JSON Schema 2020-12 exports for provisional M20-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_03.v1 import (
    M2003_CONTRACT_VERSION,
    M2003_DOSSIER_SHA256,
    M2003_DOSSIER_SLICE,
    M2003_GATE,
    M2003_M2002_INPUT_MEDIA_TYPE,
    M2003_MAX_CANONICAL_REQUEST_BYTES,
    M2003_MODULE_ID,
    M2003_OUTPUT_MEDIA_TYPE,
    M2003_OWNER,
    M2003_PARENT,
    M2003_PROVISIONAL_ABI,
    M2003_SAFETY_CLASS,
    AggregationConfiguration,
    DisagreementRecord,
    FuseProteinSubtypeEvidenceRequest,
    FusionFinding,
    IntegratedEvidenceObject,
    ProteinSubtypeIntegratedEvidenceResult,
    SourceContribution,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2003_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "integrated-evidence",
    "contribution",
    "disagreement",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": FuseProteinSubtypeEvidenceRequest,
    "output": ProteinSubtypeIntegratedEvidenceResult,
    "integrated-evidence": IntegratedEvidenceObject,
    "contribution": SourceContribution,
    "disagreement": DisagreementRecord,
    "configuration": AggregationConfiguration,
    "finding": FusionFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2003_MODULE_ID,
        "dossierSha256": M2003_DOSSIER_SHA256,
        "dossierSlice": M2003_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2003_OWNER,
        "safetyClass": M2003_SAFETY_CLASS,
        "gate": M2003_GATE,
        "strict": True,
        "provisionalAbi": M2003_PROVISIONAL_ABI,
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
        "parentTarget": M2003_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2003_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2003_M2002_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "protein_interaction_gnn",
        "alternateArchitecture": "protein_interaction_gnn",
        "fallbackArchitecture": "protein_complex_graph",
        "sourceAttributionRequired": True,
        "reliabilityRequired": True,
        "uncertaintyRequired": True,
        "disagreementPreservationRequired": True,
        "explicitAbstentionRequired": True,
        "humanReviewRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2003_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M20-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
