"""JSON Schema 2020-12 exports for provisional M22-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_03.v1 import (
    M2203_CONTRACT_VERSION,
    M2203_GATE,
    M2203_M2202_INPUT_MEDIA_TYPE,
    M2203_MAX_CANONICAL_REQUEST_BYTES,
    M2203_MODULE_ID,
    M2203_OUTPUT_MEDIA_TYPE,
    M2203_OWNER,
    M2203_PARENT,
    M2203_PROVISIONAL_ABI,
    M2203_SAFETY_CLASS,
    BaselineRun,
    BenchmarkDossier,
    BenchmarkFinding,
    BenchmarkMetric,
    ComponentAblation,
    ComputeMatchedComparison,
    LockedSplit,
    ProteinRnaDiscordanceInternalBenchmarkResult,
    RunProteinRnaDiscordanceInternalBenchmarkRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2203_CONTRACT_VERSION
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
    "request": RunProteinRnaDiscordanceInternalBenchmarkRequest,
    "output": ProteinRnaDiscordanceInternalBenchmarkResult,
    "dossier": BenchmarkDossier,
    "split": LockedSplit,
    "baseline": BaselineRun,
    "metric": BenchmarkMetric,
    "ablation": ComponentAblation,
    "comparison": ComputeMatchedComparison,
    "finding": BenchmarkFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2203_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2203_OWNER,
        "safetyClass": M2203_SAFETY_CLASS,
        "gate": M2203_GATE,
        "strict": True,
        "provisionalAbi": M2203_PROVISIONAL_ABI,
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
        "parentTarget": M2203_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2203_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2203_M2202_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "protein_complex_graph",
        "alternateArchitecture": "stoichiometric_factorization",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2203_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M22-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
