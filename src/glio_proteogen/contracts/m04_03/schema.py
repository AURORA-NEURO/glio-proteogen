"""JSON Schema 2020-12 exports for M04-03 raw-input ingestion."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_03.v1 import (
    M0403_CONTRACT_VERSION,
    M0403_MAX_CANONICAL_REQUEST_BYTES,
    M0403_MAX_DOCUMENT_BYTES,
    M0403_MODULE_ID,
    ApprovedProteoformRawParser,
    GenomeInputDocument,
    IngestProteoformRawInputsRequest,
    MassSpectrometryProteomeInputDocument,
    ProteoformRawInputArtifact,
    ProteoformRawInputPolicy,
    ProteoformRawInputReceipt,
    ProteoformRawInputValidationResult,
    ProteoformRawParseDiagnostic,
    PtmAnnotationInputDocument,
    TranscriptomeInputDocument,
    ValidatedProteoformRawInput,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-03:1.0.0"
CONTRACT_VERSION: Final = M0403_CONTRACT_VERSION
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
    "request": IngestProteoformRawInputsRequest,
    "output": ProteoformRawInputValidationResult,
    "policy": ProteoformRawInputPolicy,
    "parser-profile": ApprovedProteoformRawParser,
    "input-artifact": ProteoformRawInputArtifact,
    "proteome-document": MassSpectrometryProteomeInputDocument,
    "genome-document": GenomeInputDocument,
    "transcriptome-document": TranscriptomeInputDocument,
    "ptm-document": PtmAnnotationInputDocument,
    "validated-input": ValidatedProteoformRawInput,
    "diagnostic": ProteoformRawParseDiagnostic,
    "receipt": ProteoformRawInputReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only M04-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0403_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "externalContentTraversal": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "modelExecution": False,
        "eventPersistence": False,
        "parentTarget": "protein_rna_discordance",
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0403_MAX_CANONICAL_REQUEST_BYTES
    if name.endswith("-document"):
        metadata["maxDocumentBytes"] = M0403_MAX_DOCUMENT_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all installed M04-03 schemas."""

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
