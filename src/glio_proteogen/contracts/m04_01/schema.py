"""JSON Schema 2020-12 exports for M04-01."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_01.v1 import (
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    EvaluateProteoformProtocolRequest,
    IsoformDiscriminationPolicy,
    ModificationLocalizationPolicy,
    ProteinRnaDiscordanceHandoffRequirements,
    ProteoformCoordinatePolicy,
    ProteoformEvidenceEligibilityPolicy,
    ProteoformProtocolConformanceResult,
    ProteoformProtocolReceipt,
    ProteoformProtocolSchema,
    ProteoformQuantificationPolicy,
    ProteoformReferenceBundle,
    ProteoformReferenceCardinality,
    ReviewedProteoformConformanceProfile,
)

CONTRACT_VERSION: Final = "1.0.0"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-01:1.0.0"
ProteoformProtocolContractName = Literal[
    "request",
    "output",
    "protocol",
    "profile",
    "reference-bundle",
    "reference-cardinality",
    "coordinate-policy",
    "evidence-eligibility-policy",
    "isoform-discrimination-policy",
    "modification-localization-policy",
    "quantification-policy",
    "discordance-handoff",
    "receipt",
]
ContractName = ProteoformProtocolContractName
_CONTRACTS: Final = {
    "request": EvaluateProteoformProtocolRequest,
    "output": ProteoformProtocolConformanceResult,
    "protocol": ProteoformProtocolSchema,
    "profile": ReviewedProteoformConformanceProfile,
    "reference-bundle": ProteoformReferenceBundle,
    "reference-cardinality": ProteoformReferenceCardinality,
    "coordinate-policy": ProteoformCoordinatePolicy,
    "evidence-eligibility-policy": ProteoformEvidenceEligibilityPolicy,
    "isoform-discrimination-policy": IsoformDiscriminationPolicy,
    "modification-localization-policy": ModificationLocalizationPolicy,
    "quantification-policy": ProteoformQuantificationPolicy,
    "discordance-handoff": ProteinRnaDiscordanceHandoffRequirements,
    "receipt": ProteoformProtocolReceipt,
}


def contract_json_schema(name: ProteoformProtocolContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M04-01",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "signalValues": False,
        "scientificInference": False,
        "proteinRnaDiscordanceInference": False,
        "proteogenomicStateEmission": False,
        "proteotypeEmission": False,
        "proteinLevelSubtypeEmission": False,
        "proteoformInference": False,
        "proteinInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "modificationLocalization": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityOrConsentInference": False,
        "parentTarget": "protein_rna_discordance",
        "opaqueIdentifierPattern": (
            "^(request|actor|decision|schema|profile|bundle|vocabulary|reviewer|evidence)"
            r"\.[0-9a-f]{64}$"
        ),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0401_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ProteoformProtocolContractName, dict[str, object]]:
    """Return all thirteen standalone M04-01 schemas."""

    names: tuple[ProteoformProtocolContractName, ...] = (
        "request",
        "output",
        "protocol",
        "profile",
        "reference-bundle",
        "reference-cardinality",
        "coordinate-policy",
        "evidence-eligibility-policy",
        "isoform-discrimination-policy",
        "modification-localization-policy",
        "quantification-policy",
        "discordance-handoff",
        "receipt",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "ProteoformProtocolContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
