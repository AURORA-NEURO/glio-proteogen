"""JSON Schema 2020-12 exports for provisional M19-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_01.v1 import (
    M1901_CONTRACT_VERSION,
    M1901_GATE,
    M1901_MAX_CANONICAL_REQUEST_BYTES,
    M1901_MODULE_ID,
    M1901_OUTPUT_MEDIA_TYPE,
    M1901_OWNER,
    M1901_PARENT,
    M1901_PROVISIONAL_ABI,
    M1901_SAFETY_CLASS,
    CompatibilityDecision,
    CompatibilityReport,
    CompatibilityRule,
    ProteotypeUpstreamResolutionResult,
    ResolveProteotypeUpstreamContractsRequest,
    ResolverConfiguration,
    ResolverFinding,
    UpstreamCandidate,
    ValidatedUpstreamBundle,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1901_CONTRACT_VERSION
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
    "request": ResolveProteotypeUpstreamContractsRequest,
    "output": ProteotypeUpstreamResolutionResult,
    "candidate": UpstreamCandidate,
    "compatibility-rule": CompatibilityRule,
    "compatibility-decision": CompatibilityDecision,
    "compatibility-report": CompatibilityReport,
    "configuration": ResolverConfiguration,
    "bundle": ValidatedUpstreamBundle,
    "finding": ResolverFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1901_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1901_OWNER,
        "safetyClass": M1901_SAFETY_CLASS,
        "gate": M1901_GATE,
        "strict": True,
        "provisionalAbi": M1901_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1901_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1901_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "pca_ica_baseline",
        "alternateArchitecture": "multi_block_pls",
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
        "closedCandidateOutcomeBuckets": ("selected", "rejected", "unresolved"),
        "emptySelectionAllowed": True,
        "resultIdRule": "result.<request_digest_without_sha256_prefix>",
        "canonicalReplayRequired": True,
        "safeAbstentionSupportStatuses": ("limited", "unsupported", "review_required"),
        "allSevenUncertaintyDimensions": True,
        "provenanceModuleBinding": M1901_MODULE_ID,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1901_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M19-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
