"""JSON Schema 2020-12 exports for provisional M24-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_03.v1 import (
    M2403_CONTRACT_VERSION,
    M2403_GATE,
    M2403_M2402_INPUT_MEDIA_TYPE,
    M2403_MAX_CANONICAL_REQUEST_BYTES,
    M2403_MODULE_ID,
    M2403_OUTPUT_MEDIA_TYPE,
    M2403_OWNER,
    M2403_PARENT,
    M2403_PROVISIONAL_ABI,
    M2403_SAFETY_CLASS,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkMetric,
    BiomarkerPanelInternalBenchmarkResult,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunBiomarkerPanelInternalBenchmarkRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M24-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2403_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "dossier",
    "split",
    "baseline",
    "metric",
    "ablation",
    "comparison",
    "finding",
]
_CONTRACTS: Final = {
    "request": RunBiomarkerPanelInternalBenchmarkRequest,
    "output": BiomarkerPanelInternalBenchmarkResult,
    "dossier": BenchmarkDossier,
    "split": LockedSplit,
    "baseline": BaselineRun,
    "metric": BenchmarkMetric,
    "ablation": ComponentAblation,
    "comparison": ComputeMatchedComparison,
    "finding": BenchmarkFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M24-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2403_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2403_OWNER,
        "safetyClass": M2403_SAFETY_CLASS,
        "gate": M2403_GATE,
        "strict": True,
        "provisionalAbi": M2403_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2403_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2403_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2403_M2402_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "stoichiometric_factorization",
        "alternateArchitecture": "pathway_activity_network",
        "fallbackArchitecture": "protein_complex_graph",
        "batchMissingProteinSensitivity": True,
        "stoichiometricFactorizationRequired": True,
        "nestedValidationRequired": True,
        "lockedSplitsRequired": True,
        "simpleBaselineRequired": True,
        "matureBaselineRequired": True,
        "componentAblationRequired": True,
        "computeMatchedComparisonRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2403_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M24-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
