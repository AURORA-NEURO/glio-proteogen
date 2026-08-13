"""JSON Schema 2020-12 exports for M03-07 support routing."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_07.v1 import (
    M0307_CONTRACT_VERSION,
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    M0307_MODULE_ID,
    ProteinInferenceAbstention,
    ProteinInferenceContextReceipt,
    ProteinInferenceDeclaredSupportFact,
    ProteinInferenceDimensionAssessment,
    ProteinInferenceDimensionRemediation,
    ProteinInferenceEnvelopeAssessment,
    ProteinInferenceHarmonizationSupportReceipt,
    ProteinInferenceQualitySupportReceipt,
    ProteinInferenceSupportEnvelope,
    ProteinInferenceSupportPolicy,
    ProteinInferenceSupportPrerequisites,
    ProteinInferenceSupportProfile,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-07:1.0.0"
CONTRACT_VERSION: Final = M0307_CONTRACT_VERSION
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
    "request": RouteProteinInferenceSupportRequest,
    "output": ProteinInferenceSupportRouteResult,
    "prerequisites": ProteinInferenceSupportPrerequisites,
    "quality-receipt": ProteinInferenceQualitySupportReceipt,
    "harmonization-receipt": ProteinInferenceHarmonizationSupportReceipt,
    "fact": ProteinInferenceDeclaredSupportFact,
    "context-receipt": ProteinInferenceContextReceipt,
    "profile": ProteinInferenceSupportProfile,
    "policy": ProteinInferenceSupportPolicy,
    "envelope": ProteinInferenceSupportEnvelope,
    "remediation": ProteinInferenceDimensionRemediation,
    "dimension-assessment": ProteinInferenceDimensionAssessment,
    "envelope-assessment": ProteinInferenceEnvelopeAssessment,
    "abstention": ProteinInferenceAbstention,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0307_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayloadInSchema": False,
        "proteinInference": False,
        "proteoformInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
        "calibratedProbability": False,
        "opaqueIdentifierPattern": (
            "^(request|profile|policy|envelope|specimen|disease|reference|use|reason|"
            r"remediation|evidence|reviewer|route)\.[0-9a-f]{64}$"
        ),
        **({"maxRequestBytes": M0307_MAX_CANONICAL_REQUEST_BYTES} if name == "request" else {}),
    }
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
