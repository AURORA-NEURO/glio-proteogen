"""JSON Schema 2020-12 exports for provisional M15-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_08.v1 import (
    M1508_CONTRACT_VERSION,
    M1508_DOSSIER_SHA256,
    M1508_DOSSIER_SLICE,
    M1508_GATE,
    M1508_M1507_INPUT_MEDIA_TYPE,
    M1508_MAX_CANONICAL_REQUEST_BYTES,
    M1508_MODULE_ID,
    M1508_OUTPUT_MEDIA_TYPE,
    M1508_OWNER,
    M1508_PARENT,
    M1508_PROVISIONAL_ABI,
    M1508_SAFETY_CLASS,
    AssembleComplexActivityMechanismDossierRequest,
    ClaimCeiling,
    ComplexActivityMechanismDossierResult,
    CounterEvidenceRecord,
    MechanismDossierConfiguration,
    MechanismDossierDiagnostic,
    MechanismEvidenceDossier,
    MechanismEvidenceLink,
    ValidationRoute,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1508_CONTRACT_VERSION
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
    "request": AssembleComplexActivityMechanismDossierRequest,
    "output": ComplexActivityMechanismDossierResult,
    "dossier": MechanismEvidenceDossier,
    "link": MechanismEvidenceLink,
    "counter-evidence": CounterEvidenceRecord,
    "validation-route": ValidationRoute,
    "claim-ceiling": ClaimCeiling,
    "configuration": MechanismDossierConfiguration,
    "diagnostic": MechanismDossierDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1508_MODULE_ID,
        "dossierSha256": M1508_DOSSIER_SHA256,
        "dossierSlice": M1508_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1508_OWNER,
        "safetyClass": M1508_SAFETY_CLASS,
        "gate": M1508_GATE,
        "strict": True,
        "provisionalAbi": M1508_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1508_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1508_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1508_M1507_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "conformal_proteotype",
        "alternateArchitecture": "conformal_proteotype",
        "fallbackArchitecture": "baseline_stack",
        "reconstructableChainRequired": True,
        "counterEvidenceRequired": True,
        "validationRouteRequired": True,
        "claimCeilingRequired": True,
        "weakLinksMustRemainVisible": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1508_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M15-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
