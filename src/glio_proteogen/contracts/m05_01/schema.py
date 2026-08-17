"""JSON Schema 2020-12 exports for M05-01."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_01.v1 import (
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationAssaySpecimenPolicy,
    PtmLocalizationCompatibilityRule,
    PtmLocalizationControlledVocabulary,
    PtmLocalizationMetadataFieldPolicy,
    PtmLocalizationProtocolConformanceResult,
    PtmLocalizationProtocolReceipt,
    PtmLocalizationProtocolSchema,
    PtmLocalizationReferenceBundle,
    PtmLocalizationReferenceCardinality,
    PtmLocalizationUnitPolicy,
    ReviewedPtmLocalizationConformanceProfile,
    VariantPeptideHandoffRequirements,
)

CONTRACT_VERSION: Final = "1.0.0"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-01:1.0.0"
PtmLocalizationProtocolContractName = Literal[
    "request",
    "output",
    "protocol",
    "profile",
    "reference-bundle",
    "reference-cardinality",
    "controlled-vocabulary",
    "unit-policy",
    "metadata-field-policy",
    "compatibility-policy",
    "assay-specimen-policy",
    "variant-peptide-handoff",
    "receipt",
]
ContractName = PtmLocalizationProtocolContractName
_CONTRACTS: Final = {
    "request": EvaluatePtmLocalizationProtocolRequest,
    "output": PtmLocalizationProtocolConformanceResult,
    "protocol": PtmLocalizationProtocolSchema,
    "profile": ReviewedPtmLocalizationConformanceProfile,
    "reference-bundle": PtmLocalizationReferenceBundle,
    "reference-cardinality": PtmLocalizationReferenceCardinality,
    "controlled-vocabulary": PtmLocalizationControlledVocabulary,
    "unit-policy": PtmLocalizationUnitPolicy,
    "metadata-field-policy": PtmLocalizationMetadataFieldPolicy,
    "compatibility-policy": PtmLocalizationCompatibilityRule,
    "assay-specimen-policy": PtmLocalizationAssaySpecimenPolicy,
    "variant-peptide-handoff": VariantPeptideHandoffRequirements,
    "receipt": PtmLocalizationProtocolReceipt,
}


def contract_json_schema(name: PtmLocalizationProtocolContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M05-01",
        "contractVersion": CONTRACT_VERSION,
        "owner": "Quality engineering",
        "safetyClass": "S2",
        "gate": "G0",
        "strict": True,
        "rawPayload": False,
        "signalValues": False,
        "scientificInference": False,
        "ptmLocalization": False,
        "variantPeptideEmission": False,
        "proteogenomicStateEmission": False,
        "proteotypeEmission": False,
        "proteinLevelSubtypeEmission": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityOrConsentInference": False,
        "parentTarget": "variant_peptide",
        "opaqueIdentifierPattern": _opaque_identifier_pattern(),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0501_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def _opaque_identifier_pattern() -> str:
    return (
        r"^(?:(?:request|actor|decision|schema|profile|bundle|vocabulary|term|unit|field|rule|"
        r"policy|reviewer|evidence)\.[0-9a-f]{64}|(?:result|finding|activity)\.m0501\."
        r"[0-9a-f]{64})$"
    )


def contract_json_schemas() -> dict[PtmLocalizationProtocolContractName, dict[str, object]]:
    """Return all thirteen standalone M05-01 schemas."""

    names: tuple[PtmLocalizationProtocolContractName, ...] = (
        "request",
        "output",
        "protocol",
        "profile",
        "reference-bundle",
        "reference-cardinality",
        "controlled-vocabulary",
        "unit-policy",
        "metadata-field-policy",
        "compatibility-policy",
        "assay-specimen-policy",
        "variant-peptide-handoff",
        "receipt",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "PtmLocalizationProtocolContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
