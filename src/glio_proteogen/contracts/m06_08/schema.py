"""JSON Schema 2020-12 exports for provisional M06-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_08.v1 import (
    M0608_CONTRACT_VERSION,
    M0608_GATE,
    M0608_MAX_CANONICAL_REQUEST_BYTES,
    M0608_MODULE_ID,
    M0608_OUTPUT_MEDIA_TYPE,
    M0608_OWNER,
    M0608_PARENT,
    M0608_SAFETY_CLASS,
    ProteinAbundanceEvidenceBundle,
    ProteinAbundanceEvidencePublicationResult,
    ProteinAbundanceExplanation,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublisherDiagnostic,
    PublishProteinAbundanceEvidenceRequest,
    ReconstructionStep,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M0608_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "evidence-bundle",
    "explanation",
    "assumption",
    "counter-evidence",
    "diagnostic",
    "reconstruction-step",
]
_CONTRACTS: Final = {
    "request": PublishProteinAbundanceEvidenceRequest,
    "output": ProteinAbundanceEvidencePublicationResult,
    "evidence-bundle": ProteinAbundanceEvidenceBundle,
    "explanation": ProteinAbundanceExplanation,
    "assumption": PublisherAssumption,
    "counter-evidence": PublisherCounterEvidence,
    "diagnostic": PublisherDiagnostic,
    "reconstruction-step": ReconstructionStep,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M06-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0608_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0608_OWNER,
        "safetyClass": M0608_SAFETY_CLASS,
        "gate": M0608_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0608_PARENT,
        "variantPeptideEmission": False,
        "sourcesRequiredForPublication": True,
        "assumptionsRequiredForPublication": True,
        "counterEvidenceRequiredForPublication": True,
        "reconstructionEvidenceRequiredForPublication": True,
        "outputMediaType": M0608_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0608_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M06-08 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
