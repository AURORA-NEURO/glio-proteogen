"""JSON Schema 2020-12 exports for provisional M13-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_08.v1 import (
    M1308_CONTRACT_VERSION,
    M1308_GATE,
    M1308_MAX_CANONICAL_REQUEST_BYTES,
    M1308_MODULE_ID,
    M1308_OUTPUT_MEDIA_TYPE,
    M1308_OWNER,
    M1308_PARENT,
    M1308_PROVISIONAL_ABI,
    M1308_SAFETY_CLASS,
    AssembleProteotypeMechanismDossierRequest,
    ClaimCeiling,
    CounterEvidenceRecord,
    MechanismDossierConfiguration,
    MechanismDossierDiagnostic,
    MechanismEvidenceDossier,
    MechanismEvidenceLink,
    ProteotypeMechanismDossierResult,
    ValidationRoute,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M13-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1308_CONTRACT_VERSION
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
    "request": AssembleProteotypeMechanismDossierRequest,
    "output": ProteotypeMechanismDossierResult,
    "dossier": MechanismEvidenceDossier,
    "link": MechanismEvidenceLink,
    "counter-evidence": CounterEvidenceRecord,
    "validation-route": ValidationRoute,
    "claim-ceiling": ClaimCeiling,
    "configuration": MechanismDossierConfiguration,
    "diagnostic": MechanismDossierDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M13-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1308_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1308_OWNER,
        "safetyClass": M1308_SAFETY_CLASS,
        "gate": M1308_GATE,
        "strict": True,
        "provisionalAbi": M1308_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1308_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1308_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m13-07+json",
        "primaryArchitecture": "bayesian_model_averaging",
        "alternateArchitecture": "disagreement_review_ensemble",
        "fallbackArchitecture": "baseline_stack",
        "reconstructableChainRequired": True,
        "counterEvidenceRequired": True,
        "validationRouteRequired": True,
        "claimCeilingRequired": True,
        "weakLinksMustRemainVisible": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1308_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M13-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
