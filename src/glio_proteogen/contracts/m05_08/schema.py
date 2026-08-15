"""JSON Schema 2020-12 exports for the provisional M05-08 package spine."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_08.v1 import (
    M0508_CONTRACT_VERSION,
    M0508_GATE,
    M0508_MAX_CANONICAL_REQUEST_BYTES,
    M0508_MAX_PACKAGE_BYTES,
    M0508_MODULE_ID,
    M0508_OUTPUT_MEDIA_TYPE,
    M0508_OWNER,
    M0508_PARENT,
    M0508_PROVISIONAL_ABI,
    M0508_SAFETY_CLASS,
    BuildPtmLocalizationReleaseRequest,
    PtmLocalizationReleaseArtifact,
    PtmLocalizationReleaseManifest,
    PtmLocalizationReleasePolicy,
    PtmLocalizationReleaseQuarantine,
    PtmLocalizationReleaseResult,
    PtmLocalizationReleaseSignature,
    PtmLocalizationReleaseVerification,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-08:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0508_CONTRACT_VERSION
PtmLocalizationReleaseContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "signature",
    "quarantine",
    "verification",
]
ContractName = PtmLocalizationReleaseContractName

_CONTRACTS: Final = {
    "request": BuildPtmLocalizationReleaseRequest,
    "output": PtmLocalizationReleaseResult,
    "policy": PtmLocalizationReleasePolicy,
    "artifact": PtmLocalizationReleaseArtifact,
    "manifest": PtmLocalizationReleaseManifest,
    "signature": PtmLocalizationReleaseSignature,
    "quarantine": PtmLocalizationReleaseQuarantine,
    "verification": PtmLocalizationReleaseVerification,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema; field names are provisional and not frozen ABI."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0508_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0508_OWNER,
        "safetyClass": M0508_SAFETY_CLASS,
        "gate": M0508_GATE,
        "strict": True,
        "provisionalAbi": M0508_PROVISIONAL_ABI,
        "provisionalFixtures": True,
        "provisionalLimits": True,
        "rawPayload": False,
        "immutableProvenance": True,
        "signedReleasePackage": True,
        "reproducibilityManifest": True,
        "parentTarget": M0508_PARENT,
        "outputMediaType": M0508_OUTPUT_MEDIA_TYPE,
        "maxPackageBytes": M0508_MAX_PACKAGE_BYTES,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0508_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all provisional schemas in their declared ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "ContractName",
    "PtmLocalizationReleaseContractName",
    "SCHEMA_ID_PREFIX",
    "contract_json_schema",
    "contract_json_schemas",
]
