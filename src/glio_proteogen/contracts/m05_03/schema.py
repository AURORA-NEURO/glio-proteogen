"""JSON Schema 2020-12 exports for M05-03 raw-input ingestion."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_03.v1 import (
    M0503_CONTRACT_VERSION,
    M0503_MAX_CANONICAL_REQUEST_BYTES,
    M0503_MAX_DOCUMENT_BYTES,
    M0503_MODULE_ID,
    ApprovedPtmLocalizationRawParser,
    GenomeInputDocument,
    IngestPtmLocalizationRawInputsRequest,
    MassSpectrometryProteomeInputDocument,
    PtmAnnotationInputDocument,
    PtmLocalizationRawInputArtifact,
    PtmLocalizationRawInputPolicy,
    PtmLocalizationRawInputReceipt,
    PtmLocalizationRawInputValidationResult,
    PtmLocalizationRawParseDiagnostic,
    TranscriptomeInputDocument,
    ValidatedPtmLocalizationRawInput,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-03:1.0.0"
CONTRACT_VERSION: Final = M0503_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "parser-profile",
    "input-artifact",
    "proteome-document",
    "genome-document",
    "transcriptome-document",
    "ptm-document",
    "validated-input",
    "diagnostic",
    "receipt",
]
_CONTRACTS: Final = {
    "request": IngestPtmLocalizationRawInputsRequest,
    "output": PtmLocalizationRawInputValidationResult,
    "policy": PtmLocalizationRawInputPolicy,
    "parser-profile": ApprovedPtmLocalizationRawParser,
    "input-artifact": PtmLocalizationRawInputArtifact,
    "proteome-document": MassSpectrometryProteomeInputDocument,
    "genome-document": GenomeInputDocument,
    "transcriptome-document": TranscriptomeInputDocument,
    "ptm-document": PtmAnnotationInputDocument,
    "validated-input": ValidatedPtmLocalizationRawInput,
    "diagnostic": PtmLocalizationRawParseDiagnostic,
    "receipt": PtmLocalizationRawInputReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only M05-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0503_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "externalContentTraversal": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "ptm_localizationInference": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "modelExecution": False,
        "eventPersistence": False,
        "parentTarget": "variant_peptide",
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0503_MAX_CANONICAL_REQUEST_BYTES
    if name.endswith("-document"):
        metadata["maxDocumentBytes"] = M0503_MAX_DOCUMENT_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all installed M05-03 schemas."""

    names: tuple[ContractName, ...] = (
        "request",
        "output",
        "policy",
        "parser-profile",
        "input-artifact",
        "proteome-document",
        "genome-document",
        "transcriptome-document",
        "ptm-document",
        "validated-input",
        "diagnostic",
        "receipt",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
