"""JSON Schema 2020-12 exports for provisional M10-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_08.v1 import (
    M1008_CONTRACT_VERSION,
    M1008_GATE,
    M1008_MAX_CANONICAL_REQUEST_BYTES,
    M1008_MODULE_ID,
    M1008_OUTPUT_MEDIA_TYPE,
    M1008_OWNER,
    M1008_PARENT,
    M1008_SAFETY_CLASS,
    ProteinRnaEvidenceBundle,
    ProteinRnaEvidencePublicationResult,
    ProteinRnaExplanation,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherDiagnostic,
    PublisherEvidenceSource,
    PublishProteinRnaEvidenceRequest,
    ReconstructionStep,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M1008_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "evidence-bundle",
    "explanation",
    "source",
    "assumption",
    "counter-evidence",
    "diagnostic",
    "reconstruction-step",
]
_CONTRACTS: Final = {
    "request": PublishProteinRnaEvidenceRequest,
    "output": ProteinRnaEvidencePublicationResult,
    "evidence-bundle": ProteinRnaEvidenceBundle,
    "explanation": ProteinRnaExplanation,
    "source": PublisherEvidenceSource,
    "assumption": PublisherAssumption,
    "counter-evidence": PublisherCounterEvidence,
    "diagnostic": PublisherDiagnostic,
    "reconstruction-step": ReconstructionStep,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1008_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1008_OWNER,
        "safetyClass": M1008_SAFETY_CLASS,
        "gate": M1008_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1008_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1008_OUTPUT_MEDIA_TYPE,
        "upstreamResultMediaType": "application/vnd.glio-proteogen.m10-07+json",
        "sourcesRequiredForPublication": True,
        "assumptionsRequiredForPublication": True,
        "counterEvidenceRequiredForPublication": True,
        "reconstructionEvidenceRequiredForPublication": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1008_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M10-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
