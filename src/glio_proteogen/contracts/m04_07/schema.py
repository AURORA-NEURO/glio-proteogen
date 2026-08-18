"""JSON Schema 2020-12 exports for M04-07 support routing."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_07.v1 import (
    M0407_CONTRACT_VERSION,
    M0407_MAX_CANONICAL_REQUEST_BYTES,
    M0407_MODULE_ID,
    M0407_OUTPUT_MEDIA_TYPE,
    ProteoformAbstention,
    ProteoformContextReceipt,
    ProteoformDeclaredSupportFact,
    ProteoformDimensionAssessment,
    ProteoformDimensionRemediation,
    ProteoformEnvelopeAssessment,
    ProteoformHarmonizationSupportReceipt,
    ProteoformQualitySupportReceipt,
    ProteoformSupportEnvelope,
    ProteoformSupportPolicy,
    ProteoformSupportPrerequisites,
    ProteoformSupportProfile,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-07:1.0.0"
CONTRACT_VERSION: Final = M0407_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "prerequisites",
    "quality-receipt",
    "harmonization-receipt",
    "fact",
    "context-receipt",
    "profile",
    "policy",
    "envelope",
    "remediation",
    "dimension-assessment",
    "envelope-assessment",
    "abstention",
]
_CONTRACTS: Final = {
    "request": RouteProteoformSupportRequest,
    "output": ProteoformSupportRouteResult,
    "prerequisites": ProteoformSupportPrerequisites,
    "quality-receipt": ProteoformQualitySupportReceipt,
    "harmonization-receipt": ProteoformHarmonizationSupportReceipt,
    "fact": ProteoformDeclaredSupportFact,
    "context-receipt": ProteoformContextReceipt,
    "profile": ProteoformSupportProfile,
    "policy": ProteoformSupportPolicy,
    "envelope": ProteoformSupportEnvelope,
    "remediation": ProteoformDimensionRemediation,
    "dimension-assessment": ProteoformDimensionAssessment,
    "envelope-assessment": ProteoformEnvelopeAssessment,
    "abstention": ProteoformAbstention,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0407_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayloadInSchema": False,
        "proteinRnaDiscordance": False,
        "proteogenomicState": False,
        "proteotype": False,
        "proteinLevelSubtype": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "modificationLocalization": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
        "cnToProteinRegression": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "modelExecution": False,
        "calibratedProbability": False,
        "outputMediaType": M0407_OUTPUT_MEDIA_TYPE,
        "opaqueIdentifierPattern": (
            "^(request|profile|policy|envelope|specimen|disease|reference|use|reason|"
            r"remediation|evidence|reviewer|route)\.[0-9a-f]{64}$"
        ),
        **({"maxRequestBytes": M0407_MAX_CANONICAL_REQUEST_BYTES} if name == "request" else {}),
    }
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
