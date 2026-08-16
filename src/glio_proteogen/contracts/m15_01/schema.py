"""JSON Schema 2020-12 exports for provisional M15-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_01.v1 import (
    M1501_CONTRACT_VERSION,
    M1501_GATE,
    M1501_MAX_CANONICAL_REQUEST_BYTES,
    M1501_MODULE_ID,
    M1501_OUTPUT_MEDIA_TYPE,
    M1501_OWNER,
    M1501_PARENT,
    M1501_PROVISIONAL_ABI,
    M1501_SAFETY_CLASS,
    BiologicalHypothesis,
    CompetingExplanation,
    ComplexActivityHypothesisRegistryResult,
    EvidenceTier,
    FalsificationEvaluation,
    FalsificationRule,
    HypothesisEvaluation,
    HypothesisFinding,
    HypothesisRegistry,
    RegisterComplexActivityHypothesesRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1501_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "hypothesis",
    "competing-explanation",
    "falsification-rule",
    "evidence-tier",
    "registry",
    "evaluation",
    "falsification-evaluation",
    "finding",
]
_CONTRACTS: Final = {
    "request": RegisterComplexActivityHypothesesRequest,
    "output": ComplexActivityHypothesisRegistryResult,
    "hypothesis": BiologicalHypothesis,
    "competing-explanation": CompetingExplanation,
    "falsification-rule": FalsificationRule,
    "evidence-tier": EvidenceTier,
    "registry": HypothesisRegistry,
    "evaluation": HypothesisEvaluation,
    "falsification-evaluation": FalsificationEvaluation,
    "finding": HypothesisFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1501_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1501_OWNER,
        "safetyClass": M1501_SAFETY_CLASS,
        "gate": M1501_GATE,
        "strict": True,
        "provisionalAbi": M1501_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1501_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1501_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "sparse_nmf",
        "alternateArchitecture": "sparse_nmf",
        "fallbackArchitecture": "pca_ica_baseline",
        "competingExplanationsRequired": True,
        "falsificationRulesRequired": True,
        "evidenceTiersRequired": True,
        "prohibitedInterpretationsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1501_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M15-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
