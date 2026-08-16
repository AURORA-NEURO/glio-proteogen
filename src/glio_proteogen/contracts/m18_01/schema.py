"""JSON Schema 2020-12 exports for provisional M18-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_01.v1 import (
    M1801_CONTRACT_VERSION,
    M1801_GATE,
    M1801_MAX_CANONICAL_REQUEST_BYTES,
    M1801_MODULE_ID,
    M1801_OUTPUT_MEDIA_TYPE,
    M1801_OWNER,
    M1801_PARENT,
    M1801_PROVISIONAL_ABI,
    M1801_SAFETY_CLASS,
    BiomarkerPanelUpstreamResolutionResult,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    ResolveBiomarkerPanelUpstreamContractsRequest,
    ResolverConfiguration,
    ResolverFinding,
    UpstreamCandidate,
    ValidatedUpstreamBundle,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-01:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1801_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "candidate",
    "compatibility-rule",
    "compatibility-decision",
    "compatibility-report",
    "configuration",
    "bundle",
    "finding",
]
_CONTRACTS: Final = {
    "request": ResolveBiomarkerPanelUpstreamContractsRequest,
    "output": BiomarkerPanelUpstreamResolutionResult,
    "candidate": UpstreamCandidate,
    "compatibility-rule": CompatibilityRule,
    "compatibility-decision": CompatibilityDecision,
    "compatibility-report": CompatibilityReport,
    "configuration": ResolverConfiguration,
    "bundle": ValidatedUpstreamBundle,
    "finding": ResolverFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1801_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1801_OWNER,
        "safetyClass": M1801_SAFETY_CLASS,
        "gate": M1801_GATE,
        "strict": True,
        "provisionalAbi": M1801_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1801_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1801_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "multi_block_pls",
        "alternateArchitecture": "consensus_clustering",
        "fallbackArchitecture": "pca_ica_baseline",
        "typedDiscoveryRequired": True,
        "versionCompatibilityRequired": True,
        "consentRequired": True,
        "intendedUseRequired": True,
        "supportRequired": True,
        "provenancePreserved": True,
        "uncertaintyRequired": True,
        "typedRejectionsRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1801_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M18-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
