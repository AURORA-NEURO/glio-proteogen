"""JSON Schema 2020-12 exports for provisional M14-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_01.v1 import (
    M1401_CONTRACT_VERSION,
    M1401_GATE,
    M1401_MAX_CANONICAL_REQUEST_BYTES,
    M1401_MODULE_ID,
    M1401_OUTPUT_MEDIA_TYPE,
    M1401_OWNER,
    M1401_PARENT,
    M1401_PROVISIONAL_ABI,
    M1401_SAFETY_CLASS,
    BiologicalHypothesis,
    CompetingExplanation,
    EvidenceTier,
    FalsificationEvaluation,
    FalsificationRule,
    HypothesisEvaluation,
    HypothesisFinding,
    HypothesisRegistry,
    ProteinSubtypeHypothesisRegistryResult,
    RegisterProteinSubtypeHypothesesRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1401_CONTRACT_VERSION
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
    "request": RegisterProteinSubtypeHypothesesRequest,
    "output": ProteinSubtypeHypothesisRegistryResult,
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
    """Return one strict, metadata-only provisional M14-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1401_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1401_OWNER,
        "safetyClass": M1401_SAFETY_CLASS,
        "gate": M1401_GATE,
        "strict": True,
        "provisionalAbi": M1401_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1401_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1401_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "pca_ica_baseline",
        "alternateArchitecture": "multi_block_pls",
        "fallbackArchitecture": "pca_ica_baseline",
        "competingExplanationsRequired": True,
        "falsificationRulesRequired": True,
        "evidenceTiersRequired": True,
        "prohibitedInterpretationsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1401_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M14-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
