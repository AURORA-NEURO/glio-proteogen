"""JSON Schema 2020-12 exports for provisional M21-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_03.v1 import (
    M2103_CONTRACT_VERSION,
    M2103_DOSSIER_SHA256,
    M2103_DOSSIER_SLICE,
    M2103_GATE,
    M2103_M2102_INPUT_MEDIA_TYPE,
    M2103_MAX_CANONICAL_REQUEST_BYTES,
    M2103_MODULE_ID,
    M2103_OUTPUT_MEDIA_TYPE,
    M2103_OWNER,
    M2103_PARENT,
    M2103_PROVISIONAL_ABI,
    M2103_SAFETY_CLASS,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkMetric,
    ComplexActivityInternalBenchmarkResult,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    RunComplexActivityInternalBenchmarkRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2103_CONTRACT_VERSION
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
    "request": RunComplexActivityInternalBenchmarkRequest,
    "output": ComplexActivityInternalBenchmarkResult,
    "dossier": BenchmarkDossier,
    "split": LockedSplit,
    "baseline": BaselineRun,
    "metric": BenchmarkMetric,
    "ablation": ComponentAblation,
    "comparison": ComputeMatchedComparison,
    "finding": BenchmarkFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2103_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2103_OWNER,
        "safetyClass": M2103_SAFETY_CLASS,
        "gate": M2103_GATE,
        "strict": True,
        "provisionalAbi": M2103_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "dossierSha256": M2103_DOSSIER_SHA256,
        "dossierSlice": M2103_DOSSIER_SLICE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2103_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2103_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2103_M2102_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "signed_pathway_propagation",
        "alternateArchitecture": "protein_complex_graph",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2103_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M21-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
