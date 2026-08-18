"""JSON Schema 2020-12 exports for M03-08 protein-inference release packaging."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_08.v1 import (
    M0308_MAX_CANONICAL_REQUEST_BYTES,
    M0308_MAX_PACKAGE_BYTES,
    BuildProteinInferenceReleaseRequest,
    ExternalProteinInferenceSignature,
    ProteinInferenceReleaseArtifact,
    ProteinInferenceReleasePolicy,
    ProteinInferenceReleaseResult,
    ProteinInferenceReleaseVerification,
    ProteinInferenceReproducibilityManifest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-08:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ProteinInferenceReleaseContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "verification",
    "signature",
]
ContractName = ProteinInferenceReleaseContractName
_CONTRACTS: Final = {
    "request": BuildProteinInferenceReleaseRequest,
    "output": ProteinInferenceReleaseResult,
    "policy": ProteinInferenceReleasePolicy,
    "artifact": ProteinInferenceReleaseArtifact,
    "manifest": ProteinInferenceReproducibilityManifest,
    "verification": ProteinInferenceReleaseVerification,
    "signature": ExternalProteinInferenceSignature,
}


def contract_json_schema(name: ProteinInferenceReleaseContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M03-08",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "complexActivityInference": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "kinaseActivityInference": False,
        "signsRelease": False,
        "authenticatesSigner": False,
        "establishesReleaseAuthority": False,
        "exactByteReproduction": True,
        "maxPackageBytes": M0308_MAX_PACKAGE_BYTES,
        "signatureAuthorityOwnedExternally": True,
        "opaqueIdentifierPattern": (
            "^(request|actor|decision|release|policy|software|reference|build|signer|key|"
            "verifier|evidence|reviewer|parent)"
            r"\.[0-9a-f]{64}$"
        ),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0308_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ProteinInferenceReleaseContractName, dict[str, object]]:
    """Return all seven standalone M03-08 schemas."""

    names: tuple[ProteinInferenceReleaseContractName, ...] = (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "verification",
        "signature",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "ProteinInferenceReleaseContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
