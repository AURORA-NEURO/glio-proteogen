"""JSON Schema 2020-12 exports for provisional M11-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_08.v1 import (
    M1108_CONTRACT_VERSION,
    M1108_GATE,
    M1108_MAX_CANONICAL_REQUEST_BYTES,
    M1108_MAX_RECONSTRUCTION_STEPS,
    M1108_MAX_SOURCES,
    M1108_MODULE_ID,
    M1108_OUTPUT_MEDIA_TYPE,
    M1108_OWNER,
    M1108_PARENT,
    M1108_PROVISIONAL_ABI,
    M1108_SAFETY_CLASS,
    AssembleVariantPeptideMechanismDossierRequest,
    ClaimCeiling,
    CounterEvidenceRecord,
    MechanismDossierConfiguration,
    MechanismDossierDiagnostic,
    MechanismEvidenceDossier,
    MechanismEvidenceLink,
    ValidationRoute,
    VariantPeptideMechanismDossierResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M11-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1108_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "dossier",
    "link",
    "counter-evidence",
    "validation-route",
    "claim-ceiling",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": AssembleVariantPeptideMechanismDossierRequest,
    "output": VariantPeptideMechanismDossierResult,
    "dossier": MechanismEvidenceDossier,
    "link": MechanismEvidenceLink,
    "counter-evidence": CounterEvidenceRecord,
    "validation-route": ValidationRoute,
    "claim-ceiling": ClaimCeiling,
    "configuration": MechanismDossierConfiguration,
    "diagnostic": MechanismDossierDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M11-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1108_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1108_OWNER,
        "safetyClass": M1108_SAFETY_CLASS,
        "gate": M1108_GATE,
        "strict": True,
        "provisionalAbi": M1108_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1108_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1108_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m11-07+json",
        "reconstructableChainRequired": True,
        "counterEvidenceRequired": True,
        "validationRouteRequired": True,
        "claimCeilingRequired": True,
        "weakLinksMustRemainVisible": True,
        "sourceAttributionRequired": True,
        "opaqueExternalArtifacts": True,
        "sevenUncertaintyDimensions": True,
        "humanReviewForDiscrepancy": True,
        "safeAbstention": True,
        "maxSources": M1108_MAX_SOURCES,
        "maxReconstructionSteps": M1108_MAX_RECONSTRUCTION_STEPS,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1108_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M11-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
