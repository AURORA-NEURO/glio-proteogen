"""JSON Schema 2020-12 exports for provisional M16-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_01.v1 import (
    M1601_CONTRACT_VERSION,
    M1601_GATE,
    M1601_MAX_CANONICAL_REQUEST_BYTES,
    M1601_MODULE_ID,
    M1601_OUTPUT_MEDIA_TYPE,
    M1601_OWNER,
    M1601_PARENT,
    M1601_PROVISIONAL_ABI,
    M1601_SAFETY_CLASS,
    CompatibilityIssue,
    CompatibilityReport,
    ProteinRnaDiscordanceUpstreamResolutionResult,
    ResolveProteinRnaDiscordanceUpstreamRequest,
    ResolverConfiguration,
    ResolverPolicy,
    UpstreamCandidate,
    ValidatedUpstreamBundle,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1601_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "candidate",
    "compatibility-report",
    "bundle",
    "configuration",
    "policy",
    "issue",
]
_CONTRACTS: Final = {
    "request": ResolveProteinRnaDiscordanceUpstreamRequest,
    "output": ProteinRnaDiscordanceUpstreamResolutionResult,
    "candidate": UpstreamCandidate,
    "compatibility-report": CompatibilityReport,
    "bundle": ValidatedUpstreamBundle,
    "configuration": ResolverConfiguration,
    "policy": ResolverPolicy,
    "issue": CompatibilityIssue,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1601_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1601_OWNER,
        "safetyClass": M1601_SAFETY_CLASS,
        "gate": M1601_GATE,
        "strict": True,
        "provisionalAbi": M1601_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M1601_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1601_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration_bayesian_factor_analysis",
        "fallbackArchitecture": "signed_human_review_package_pca_ica",
        "typedDiscoveryRequired": True,
        "versionCompatibilityRequired": True,
        "consentRequired": True,
        "intendedUseRequired": True,
        "supportRequired": True,
        "provenanceRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "typedRejectionsRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1601_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M16-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
