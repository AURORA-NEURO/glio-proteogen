"""JSON Schema 2020-12 exports for provisional M23-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_03.v1 import (
    M2303_CONTRACT_VERSION,
    M2303_GATE,
    M2303_M2302_INPUT_MEDIA_TYPE,
    M2303_MAX_CANONICAL_REQUEST_BYTES,
    M2303_MODULE_ID,
    M2303_OUTPUT_MEDIA_TYPE,
    M2303_OWNER,
    M2303_PARENT,
    M2303_PROVISIONAL_ABI,
    M2303_SAFETY_CLASS,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkMetric,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunVariantPeptideInternalBenchmarkRequest,
    VariantPeptideInternalBenchmarkResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M23-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2303_CONTRACT_VERSION
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
    "request": RunVariantPeptideInternalBenchmarkRequest,
    "output": VariantPeptideInternalBenchmarkResult,
    "dossier": BenchmarkDossier,
    "split": LockedSplit,
    "baseline": BaselineRun,
    "metric": BenchmarkMetric,
    "ablation": ComponentAblation,
    "comparison": ComputeMatchedComparison,
    "finding": BenchmarkFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M23-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2303_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2303_OWNER,
        "safetyClass": M2303_SAFETY_CLASS,
        "gate": M2303_GATE,
        "strict": True,
        "provisionalAbi": M2303_PROVISIONAL_ABI,
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
        "parentTarget": M2303_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2303_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2303_M2302_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "pathway_activity_network",
        "alternateArchitecture": "signed_pathway_propagation",
        "fallbackArchitecture": "protein_complex_graph",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2303_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M23-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
