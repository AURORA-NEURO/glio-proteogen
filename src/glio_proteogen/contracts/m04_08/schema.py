"""JSON Schema 2020-12 exports for M04-08 release packaging."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_08.v1 import (
    M0408_MAX_CANONICAL_REQUEST_BYTES,
    M0408_MAX_PACKAGE_BYTES,
    BuildProteoformReleaseRequest,
    ExternalProteoformSignature,
    ProteoformReleaseArtifact,
    ProteoformReleasePolicy,
    ProteoformReleaseResult,
    ProteoformReleaseVerification,
    ProteoformReproducibilityManifest,
    ProteoformReproductionEvidence,
    ProteoformStageProvenance,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-08:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ProteoformReleaseContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "verification",
    "signature",
    "stage-provenance",
    "reproduction-evidence",
]
ContractName = ProteoformReleaseContractName
_CONTRACTS: Final = {
    "request": BuildProteoformReleaseRequest,
    "output": ProteoformReleaseResult,
    "policy": ProteoformReleasePolicy,
    "artifact": ProteoformReleaseArtifact,
    "manifest": ProteoformReproducibilityManifest,
    "verification": ProteoformReleaseVerification,
    "signature": ExternalProteoformSignature,
    "stage-provenance": ProteoformStageProvenance,
    "reproduction-evidence": ProteoformReproductionEvidence,
}


def contract_json_schema(name: ProteoformReleaseContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M04-08",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "proteinRnaDiscordanceInference": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "signsRelease": False,
        "authenticatesSigner": False,
        "establishesReleaseAuthority": False,
        "exactByteReproduction": True,
        "maxPackageBytes": M0408_MAX_PACKAGE_BYTES,
        "signatureAuthorityOwnedExternally": True,
        "m0407BindingRequiredForExecution": True,
        "opaqueIdentifierPattern": (
            "^(request|actor|decision|release|policy|software|reference|build|signer|key|"
            r"verifier|evidence|reviewer|parent)\.[0-9a-f]{64}$"
        ),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0408_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ProteoformReleaseContractName, dict[str, object]]:
    """Return every standalone M04-08 owned schema."""

    names: tuple[ProteoformReleaseContractName, ...] = (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "verification",
        "signature",
        "stage-provenance",
        "reproduction-evidence",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "ProteoformReleaseContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
